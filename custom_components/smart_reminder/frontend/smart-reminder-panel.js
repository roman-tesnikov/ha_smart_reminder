const STATUS_LABELS = {
  scheduled: "Запланировано",
  active: "В работе",
  snoozed: "Отложено",
};

const TYPE_LABELS = {
  once: "Однократное",
  cron: "По расписанию",
  after_completion: "С задержкой после выполнения",
};

class SmartReminderPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = undefined;
    this._loaded = false;
    this._loading = true;
    this._reminders = [];
    this._settings = {};
    this._editingId = null;
    this._editingReminder = null;
    this._initialNextTrigger = null;
  }

  set hass(value) {
    this._hass = value;
    if (this.isConnected && !this._loaded) {
      this._loaded = true;
      this._load();
    }
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    this._renderShell();
    if (this._hass && !this._loaded) {
      this._loaded = true;
      this._load();
    }
  }

  async _load() {
    this._loading = true;
    this._renderList();
    try {
      const result = await this._hass.connection.sendMessagePromise({
        type: "smart_reminder/list",
      });
      this._reminders = result.reminders || [];
      this._settings = result.settings || {};
      this._showGlobalError("");
    } catch (error) {
      this._showGlobalError(this._errorMessage(error));
    } finally {
      this._loading = false;
      this._renderList();
      this._renderDnd();
    }
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100vh;
          color: var(--primary-text-color);
          background: var(--primary-background-color);
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }
        * { box-sizing: border-box; }
        .topbar {
          position: sticky;
          top: 0;
          z-index: 4;
          display: flex;
          align-items: center;
          min-height: 64px;
          padding: 0 24px;
          color: var(--app-header-text-color, var(--text-primary-color));
          background: var(--app-header-background-color, var(--primary-color));
          box-shadow: var(--app-header-shadow, 0 2px 4px rgba(0,0,0,.18));
        }
        .topbar h1 { margin: 0; font-size: 20px; font-weight: 500; }
        main { max-width: 1280px; margin: 0 auto; padding: 28px 24px 64px; }
        .hero {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 24px;
          margin-bottom: 22px;
        }
        .hero h2 { margin: 0 0 7px; font-size: 28px; font-weight: 500; }
        .subtle { color: var(--secondary-text-color); font-size: 14px; line-height: 1.5; }
        .dnd {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          margin-top: 10px;
          padding: 6px 10px;
          border-radius: 999px;
          color: var(--secondary-text-color);
          background: var(--secondary-background-color);
          font-size: 13px;
        }
        button {
          border: 0;
          border-radius: 10px;
          padding: 10px 14px;
          color: var(--primary-text-color);
          background: var(--secondary-background-color);
          cursor: pointer;
          font: inherit;
          font-weight: 500;
        }
        button:hover { filter: brightness(.96); }
        button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible {
          outline: 2px solid var(--primary-color);
          outline-offset: 2px;
        }
        button.primary {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          color: var(--text-primary-color, white);
          background: var(--primary-color);
          white-space: nowrap;
        }
        button.icon {
          display: inline-grid;
          place-items: center;
          width: 38px;
          height: 38px;
          padding: 0;
          border-radius: 50%;
          color: var(--secondary-text-color);
          background: transparent;
        }
        button.icon:hover { color: var(--primary-color); background: var(--secondary-background-color); }
        button.danger:hover { color: var(--error-color); }
        ha-icon { --mdc-icon-size: 21px; }
        .card {
          overflow: hidden;
          border: 1px solid var(--divider-color);
          border-radius: 14px;
          background: var(--card-background-color);
          box-shadow: var(--ha-card-box-shadow, none);
        }
        table { width: 100%; border-collapse: collapse; }
        th {
          padding: 13px 16px;
          color: var(--secondary-text-color);
          background: var(--secondary-background-color);
          font-size: 12px;
          font-weight: 600;
          text-align: left;
          text-transform: uppercase;
          letter-spacing: .04em;
        }
        td { padding: 15px 16px; border-top: 1px solid var(--divider-color); vertical-align: middle; }
        tr:first-child td { border-top: 0; }
        .name { font-weight: 500; }
        .id { margin-top: 3px; color: var(--secondary-text-color); font-family: monospace; font-size: 12px; }
        .status {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          padding: 5px 9px;
          border-radius: 999px;
          font-size: 13px;
          font-weight: 500;
        }
        .status::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
        .scheduled { color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 12%, transparent); }
        .active { color: var(--warning-color, #f59e0b); background: color-mix(in srgb, var(--warning-color, #f59e0b) 13%, transparent); }
        .snoozed { color: #7c4dff; background: color-mix(in srgb, #7c4dff 12%, transparent); }
        .actions { display: flex; align-items: center; justify-content: flex-end; gap: 1px; }
        .toggle { position: relative; display: inline-flex; width: 42px; height: 24px; }
        .toggle input { width: 0; height: 0; opacity: 0; }
        .track { position: absolute; inset: 0; border-radius: 14px; background: var(--disabled-color); cursor: pointer; transition: .18s; }
        .track::after { content: ""; position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 50%; background: white; box-shadow: 0 1px 2px rgba(0,0,0,.3); transition: .18s; }
        .toggle input:checked + .track { background: var(--primary-color); }
        .toggle input:checked + .track::after { transform: translateX(18px); }
        .empty, .loading { padding: 64px 24px; color: var(--secondary-text-color); text-align: center; }
        .empty ha-icon { display: block; margin: 0 auto 14px; --mdc-icon-size: 48px; opacity: .55; }
        .error {
          display: none;
          margin-bottom: 18px;
          padding: 12px 14px;
          border-radius: 10px;
          color: var(--error-color);
          background: color-mix(in srgb, var(--error-color) 10%, transparent);
        }
        .error.visible { display: block; }
        dialog {
          width: min(720px, calc(100vw - 32px));
          max-height: calc(100vh - 32px);
          padding: 0;
          border: 0;
          border-radius: 16px;
          color: var(--primary-text-color);
          background: var(--card-background-color);
          box-shadow: 0 20px 60px rgba(0,0,0,.35);
        }
        dialog::backdrop { background: rgba(0,0,0,.52); }
        .dialog-head {
          position: sticky;
          top: 0;
          z-index: 2;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 18px 22px;
          border-bottom: 1px solid var(--divider-color);
          background: var(--card-background-color);
        }
        .dialog-head h2 { margin: 0; font-size: 21px; font-weight: 500; }
        form { padding: 22px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 17px 18px; }
        .field { display: flex; flex-direction: column; gap: 7px; }
        .field.full { grid-column: 1 / -1; }
        label { font-size: 13px; font-weight: 500; }
        input, select, textarea {
          width: 100%;
          min-height: 42px;
          padding: 9px 11px;
          border: 1px solid var(--divider-color);
          border-radius: 9px;
          color: var(--primary-text-color);
          background: var(--primary-background-color);
          font: inherit;
        }
        textarea { min-height: 78px; resize: vertical; }
        input:disabled { color: var(--disabled-text-color); background: var(--secondary-background-color); }
        .datetime-fields { display: grid; grid-template-columns: minmax(0, 1fr) minmax(100px, .55fr); gap: 9px; }
        .hint { color: var(--secondary-text-color); font-size: 12px; line-height: 1.4; }
        .check { display: flex; align-items: center; gap: 9px; min-height: 42px; }
        .check input { width: 19px; min-height: 19px; accent-color: var(--primary-color); }
        .conditional[hidden] { display: none; }
        .form-error { min-height: 20px; margin-top: 15px; color: var(--error-color); font-size: 13px; }
        .dialog-actions { display: flex; justify-content: flex-end; gap: 9px; margin-top: 5px; padding-top: 14px; }
        .mobile-list { display: none; }
        @media (max-width: 760px) {
          .topbar { min-height: 56px; padding: 0 16px; }
          main { padding: 20px 12px 48px; }
          .hero { align-items: center; }
          .hero h2 { font-size: 23px; }
          .hero .subtle.description { display: none; }
          .desktop-table { display: none; }
          .mobile-list { display: grid; gap: 10px; }
          .mobile-card { padding: 15px; border: 1px solid var(--divider-color); border-radius: 13px; background: var(--card-background-color); }
          .mobile-head { display: flex; justify-content: space-between; gap: 12px; }
          .mobile-meta { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: 14px; color: var(--secondary-text-color); font-size: 13px; }
          .mobile-actions { display: flex; justify-content: flex-end; margin: 12px -7px -7px; padding-top: 8px; border-top: 1px solid var(--divider-color); }
          .grid { grid-template-columns: 1fr; }
          .field.full { grid-column: auto; }
          dialog { width: calc(100vw - 16px); max-height: calc(100vh - 16px); }
          form { padding: 18px; }
        }
      </style>
      <div class="topbar"><h1>Умные напоминания</h1></div>
      <main>
        <section class="hero">
          <div>
            <h2>Напоминания</h2>
            <div class="subtle description">Локальное расписание с повторами, мьютом и контролем выполнения.</div>
            <div class="dnd" id="dnd"><ha-icon icon="mdi:weather-night"></ha-icon><span>DnD: загрузка…</span></div>
          </div>
          <button class="primary" id="add"><ha-icon icon="mdi:plus"></ha-icon>Добавить</button>
        </section>
        <div class="error" id="global-error"></div>
        <section id="list"></section>
      </main>
      <dialog id="editor">
        <div class="dialog-head">
          <h2 id="dialog-title">Новое напоминание</h2>
          <button class="icon" type="button" id="close" title="Закрыть"><ha-icon icon="mdi:close"></ha-icon></button>
        </div>
        <form id="form">
          <div class="grid">
            <div class="field">
              <label for="id">ID</label>
              <input id="id" name="id" required maxlength="64" pattern="[A-Za-z0-9][A-Za-z0-9_.-]{0,63}">
              <span class="hint">Латинские буквы, цифры, точка, «_» и «-».</span>
            </div>
            <div class="field">
              <label for="name">Название</label>
              <input id="name" name="name" required maxlength="200">
            </div>
            <div class="field full">
              <label for="type">Тип напоминания</label>
              <select id="type" name="reminder_type">
                <option value="once">Однократное напоминание</option>
                <option value="cron">По расписанию (crontab)</option>
                <option value="after_completion">С задержкой после выполнения</option>
              </select>
            </div>
            <div class="field conditional" data-for="scheduled-datetime">
              <label for="scheduled-date">Дата и время первого запуска</label>
              <div class="datetime-fields">
                <input id="scheduled-date" name="scheduled_date" inputmode="numeric" maxlength="10" pattern="[0-9]{2}\\.[0-9]{2}\\.[0-9]{4}" placeholder="ДД.ММ.ГГГГ" aria-label="Дата первого запуска">
                <input id="scheduled-time" name="scheduled_time" inputmode="numeric" maxlength="5" pattern="(?:[01][0-9]|2[0-3]):[0-5][0-9]" placeholder="ЧЧ:ММ" aria-label="Время первого запуска">
              </div>
              <span class="hint" id="timezone-hint"></span>
            </div>
            <div class="field conditional" data-for="next-datetime" hidden>
              <label for="next-trigger-date">Дата и время следующего запуска</label>
              <div class="datetime-fields">
                <input id="next-trigger-date" name="next_trigger_date" inputmode="numeric" maxlength="10" pattern="[0-9]{2}\\.[0-9]{2}\\.[0-9]{4}" placeholder="ДД.ММ.ГГГГ" aria-label="Дата следующего запуска">
                <input id="next-trigger-time" name="next_trigger_time" inputmode="numeric" maxlength="5" pattern="(?:[01][0-9]|2[0-3]):[0-5][0-9]" placeholder="ЧЧ:ММ" aria-label="Время следующего запуска">
              </div>
              <span class="hint" id="next-timezone-hint"></span>
            </div>
            <div class="field conditional" data-for="cron" hidden>
              <label for="cron">Crontab</label>
              <input id="cron" name="cron" placeholder="0 10 * * 1">
              <span class="hint">5 полей: минуты, часы, день месяца, месяц, день недели. Для раза в N недель: @every Nw CRON.</span>
            </div>
            <div class="field conditional" data-for="cron" hidden>
              <label for="cron-anchor-date">Якорная дата</label>
              <input id="cron-anchor-date" name="cron_anchor_date" inputmode="numeric" maxlength="10" pattern="[0-9]{2}\\.[0-9]{2}\\.[0-9]{4}" placeholder="ДД.ММ.ГГГГ">
              <span class="hint">Для @every Nw: задаёт первый день цикла, например 27.07.2026. Дата должна соответствовать дню запуска cron.</span>
            </div>
            <div class="field conditional" data-for="delay" hidden>
              <label for="delay">Задержка после выполнения, мин</label>
              <input id="delay" name="delay_minutes" type="number" min="1" value="1440">
            </div>
            <div class="field">
              <label for="repeat">Частота до выполнения, мин</label>
              <input id="repeat" name="repeat_interval_minutes" type="number" min="1" value="15" required>
            </div>
            <div class="field">
              <label for="snooze">Мьют по умолчанию, мин</label>
              <input id="snooze" name="default_snooze_minutes" type="number" min="1" value="30" required>
            </div>
            <div class="field">
              <label class="check"><input id="enabled" name="enabled" type="checkbox" checked> Включено</label>
            </div>
            <div class="field">
              <label class="check"><input id="ignore-dnd" name="ignore_dnd" type="checkbox"> Игнорировать DnD</label>
            </div>
            <div class="field full">
              <label for="first-text">Текст первого напоминания</label>
              <textarea id="first-text" name="first_text" required></textarea>
            </div>
            <div class="field full">
              <label for="repeat-text">Текст повторных напоминаний</label>
              <textarea id="repeat-text" name="repeat_text"></textarea>
              <span class="hint">Если пусто, используется текст первого напоминания.</span>
            </div>
            <div class="field full">
              <label for="snoozed-text">Текст отложенного напоминания</label>
              <textarea id="snoozed-text" name="snoozed_text"></textarea>
              <span class="hint">Передаётся в smart_reminder_snoozed сразу при нажатии «Отложить». После окончания мьюта smart_reminder_repeated использует текст повторных напоминаний.</span>
            </div>
            <div class="field full">
              <label for="completed-text">Текст выполненного напоминания</label>
              <textarea id="completed-text" name="completed_text"></textarea>
            </div>
            <div class="field full">
              <label for="recipients">ID получателей</label>
              <textarea id="recipients" name="recipient_ids" placeholder="123456789&#10;family_chat"></textarea>
              <span class="hint">По одному ID в строке или через запятую.</span>
            </div>
          </div>
          <div class="form-error" id="form-error"></div>
          <div class="dialog-actions">
            <button type="button" id="cancel">Отмена</button>
            <button type="submit" class="primary" id="save">Сохранить</button>
          </div>
        </form>
      </dialog>
    `;

    this.shadowRoot.getElementById("add").addEventListener("click", () => this._openEditor());
    this.shadowRoot.getElementById("close").addEventListener("click", () => this._closeEditor());
    this.shadowRoot.getElementById("cancel").addEventListener("click", () => this._closeEditor());
    this.shadowRoot.getElementById("type").addEventListener("change", () => this._updateConditionalFields());
    this.shadowRoot.getElementById("form").addEventListener("submit", (event) => this._save(event));
    this.shadowRoot.getElementById("list").addEventListener("click", (event) => this._handleListClick(event));
    this.shadowRoot.getElementById("list").addEventListener("change", (event) => this._handleListChange(event));
  }

  _renderDnd() {
    const element = this.shadowRoot.getElementById("dnd");
    if (!element) return;
    const start = (this._settings.dnd_start || "23:00").slice(0, 5);
    const end = (this._settings.dnd_end || "10:00").slice(0, 5);
    element.querySelector("span").textContent = `DnD: ${start}–${end} · ${this._settings.timezone || "HA"}`;
    element.title = "Изменяется в Настройки → Устройства и службы → Smart Reminder → Настроить";
  }

  _renderList() {
    const list = this.shadowRoot && this.shadowRoot.getElementById("list");
    if (!list) return;
    if (this._loading) {
      list.innerHTML = `<div class="card loading">Загрузка напоминаний…</div>`;
      return;
    }
    if (!this._reminders.length) {
      list.innerHTML = `
        <div class="card empty">
          <ha-icon icon="mdi:bell-plus-outline"></ha-icon>
          <div>Напоминаний пока нет</div>
          <div class="subtle">Создайте первое напоминание кнопкой «Добавить».</div>
        </div>`;
      return;
    }

    const rows = this._reminders.map((reminder) => `
      <tr>
        <td><div class="name">${this._escape(reminder.name)}</div><div class="id">${this._escape(reminder.id)}</div></td>
        <td>${this._toggle(reminder)}</td>
        <td><span class="status ${reminder.status}">${STATUS_LABELS[reminder.status] || reminder.status}</span></td>
        <td title="${this._escape(TYPE_LABELS[reminder.reminder_type] || reminder.reminder_type)}">${this._formatDate(reminder.next_trigger)}</td>
        <td><div class="actions">${this._actions(reminder)}</div></td>
      </tr>`).join("");

    const cards = this._reminders.map((reminder) => `
      <article class="mobile-card">
        <div class="mobile-head">
          <div><div class="name">${this._escape(reminder.name)}</div><div class="id">${this._escape(reminder.id)}</div></div>
          ${this._toggle(reminder)}
        </div>
        <div class="mobile-meta"><span class="status ${reminder.status}">${STATUS_LABELS[reminder.status] || reminder.status}</span><span>${this._formatDate(reminder.next_trigger)}</span></div>
        <div class="mobile-actions">${this._actions(reminder)}</div>
      </article>`).join("");

    list.innerHTML = `
      <div class="card desktop-table">
        <table>
          <thead><tr><th>Название</th><th>Активность</th><th>Статус</th><th>Следующий запуск</th><th style="text-align:right">Управление</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="mobile-list">${cards}</div>`;
  }

  _toggle(reminder) {
    return `<label class="toggle" title="${reminder.enabled ? "Отключить" : "Включить"}">
      <input type="checkbox" data-action="enabled" data-id="${reminder.id}" ${reminder.enabled ? "checked" : ""}>
      <span class="track"></span>
    </label>`;
  }

  _actions(reminder) {
    return `
      <button class="icon" data-action="edit" data-id="${reminder.id}" title="Редактировать"><ha-icon icon="mdi:pencil-outline"></ha-icon></button>
      <button class="icon" data-action="duplicate" data-id="${reminder.id}" title="Дублировать"><ha-icon icon="mdi:content-copy"></ha-icon></button>
      <button class="icon" data-action="snooze" data-id="${reminder.id}" title="Отложить"><ha-icon icon="mdi:bell-sleep-outline"></ha-icon></button>
      <button class="icon" data-action="complete" data-id="${reminder.id}" title="Выполнить"><ha-icon icon="mdi:check-circle-outline"></ha-icon></button>
      <button class="icon danger" data-action="delete" data-id="${reminder.id}" title="Удалить"><ha-icon icon="mdi:delete-outline"></ha-icon></button>`;
  }

  async _handleListClick(event) {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const reminder = this._reminders.find((item) => item.id === button.dataset.id);
    if (!reminder) return;
    const action = button.dataset.action;
    if (action === "edit") {
      this._openEditor(reminder);
      return;
    }
    if (action === "duplicate") {
      this._openEditor(reminder, true);
      return;
    }
    if (action === "delete" && !window.confirm(`Удалить «${reminder.name}»?`)) return;
    if (action === "complete" && !window.confirm(`Отметить «${reminder.name}» выполненным?`)) return;
    try {
      if (action === "snooze") {
        const defaultDuration = this._minutesToDuration(reminder.default_snooze_minutes);
        const duration = window.prompt("На какое время отложить? Например: 1h30m", defaultDuration);
        if (!duration) return;
        await this._send("snooze", { reminder_id: reminder.id, duration });
      } else {
        await this._send(action, { reminder_id: reminder.id });
      }
      await this._load();
    } catch (error) {
      this._showGlobalError(this._errorMessage(error));
    }
  }

  async _handleListChange(event) {
    const input = event.target.closest('input[data-action="enabled"]');
    if (!input) return;
    try {
      await this._send("set_enabled", { reminder_id: input.dataset.id, enabled: input.checked });
      await this._load();
    } catch (error) {
      input.checked = !input.checked;
      this._showGlobalError(this._errorMessage(error));
    }
  }

  _openEditor(reminder = null, duplicate = false) {
    const form = this.shadowRoot.getElementById("form");
    form.reset();
    const editing = Boolean(reminder) && !duplicate;
    this._editingId = editing ? reminder.id : null;
    this._editingReminder = editing ? reminder : null;
    let dialogTitle = "Новое напоминание";
    if (editing) dialogTitle = "Редактирование";
    if (duplicate) dialogTitle = "Дублирование напоминания";
    this.shadowRoot.getElementById("dialog-title").textContent = dialogTitle;
    const idInput = this.shadowRoot.getElementById("id");
    idInput.disabled = editing;
    idInput.value = editing ? reminder.id : this._generateReminderId();
    this.shadowRoot.getElementById("name").value = reminder ? reminder.name : "";
    this.shadowRoot.getElementById("type").value = reminder ? reminder.reminder_type : "once";
    const scheduledSource = duplicate
      ? reminder.next_trigger || reminder.scheduled_at
      : reminder && reminder.scheduled_at;
    const scheduled = this._formatForForm(
      scheduledSource || new Date(Date.now() + 3600000).toISOString(),
    );
    this.shadowRoot.getElementById("scheduled-date").value = scheduled.date;
    this.shadowRoot.getElementById("scheduled-time").value = scheduled.time;
    const nextTrigger = this._formatForForm(
      reminder && (reminder.next_trigger || reminder.scheduled_at)
        ? reminder.next_trigger || reminder.scheduled_at
        : new Date(Date.now() + 3600000).toISOString(),
    );
    this.shadowRoot.getElementById("next-trigger-date").value = nextTrigger.date;
    this.shadowRoot.getElementById("next-trigger-time").value = nextTrigger.time;
    this._initialNextTrigger = { ...nextTrigger };
    this.shadowRoot.getElementById("cron").value = reminder && reminder.cron ? reminder.cron : "0 10 * * 1";
    this.shadowRoot.getElementById("cron-anchor-date").value = reminder && reminder.cron_anchor
      ? this._formatDateOnly(reminder.cron_anchor)
      : "";
    this.shadowRoot.getElementById("delay").value = reminder && reminder.delay_minutes ? reminder.delay_minutes : 1440;
    this.shadowRoot.getElementById("repeat").value = reminder ? reminder.repeat_interval_minutes : 15;
    this.shadowRoot.getElementById("snooze").value = reminder ? reminder.default_snooze_minutes : 30;
    this.shadowRoot.getElementById("enabled").checked = reminder ? reminder.enabled : true;
    this.shadowRoot.getElementById("ignore-dnd").checked = reminder ? reminder.ignore_dnd : false;
    this.shadowRoot.getElementById("first-text").value = reminder ? reminder.first_text : "";
    this.shadowRoot.getElementById("repeat-text").value = reminder ? reminder.repeat_text || "" : "";
    this.shadowRoot.getElementById("snoozed-text").value = reminder ? reminder.snoozed_text || "" : "";
    this.shadowRoot.getElementById("completed-text").value = reminder ? reminder.completed_text || "" : "";
    this.shadowRoot.getElementById("recipients").value = reminder ? (reminder.recipient_ids || []).join("\n") : "";
    this.shadowRoot.getElementById("timezone-hint").textContent = `Часовой пояс: ${this._settings.timezone || "Home Assistant"}`;
    this.shadowRoot.getElementById("next-timezone-hint").textContent = `Часовой пояс: ${this._settings.timezone || "Home Assistant"}`;
    this.shadowRoot.getElementById("form-error").textContent = "";
    this._updateConditionalFields();
    this.shadowRoot.getElementById("editor").showModal();
  }

  _closeEditor() {
    this.shadowRoot.getElementById("editor").close();
    this._editingId = null;
    this._editingReminder = null;
    this._initialNextTrigger = null;
  }

  _updateConditionalFields() {
    const type = this.shadowRoot.getElementById("type").value;
    const editing = Boolean(this._editingId);
    this.shadowRoot.querySelector('[data-for="scheduled-datetime"]').hidden = editing || type === "cron";
    this.shadowRoot.querySelector('[data-for="next-datetime"]').hidden = !editing;
    this.shadowRoot.querySelectorAll('[data-for="cron"]').forEach((element) => {
      element.hidden = type !== "cron";
    });
    this.shadowRoot.querySelector('[data-for="delay"]').hidden = type !== "after_completion";
    const scheduledDate = this.shadowRoot.getElementById("scheduled-date");
    const scheduledTime = this.shadowRoot.getElementById("scheduled-time");
    const nextTriggerDate = this.shadowRoot.getElementById("next-trigger-date");
    const nextTriggerTime = this.shadowRoot.getElementById("next-trigger-time");
    const cron = this.shadowRoot.getElementById("cron");
    const cronAnchor = this.shadowRoot.getElementById("cron-anchor-date");
    const delay = this.shadowRoot.getElementById("delay");
    scheduledDate.required = !editing && type !== "cron";
    scheduledDate.disabled = editing || type === "cron";
    scheduledTime.required = !editing && type !== "cron";
    scheduledTime.disabled = editing || type === "cron";
    nextTriggerDate.required = editing;
    nextTriggerDate.disabled = !editing;
    nextTriggerTime.required = editing;
    nextTriggerTime.disabled = !editing;
    cron.required = type === "cron";
    cron.disabled = type !== "cron";
    cronAnchor.disabled = type !== "cron";
    delay.required = type === "after_completion";
    delay.disabled = type !== "after_completion";
  }

  async _save(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const type = form.elements.reminder_type.value;
    const error = this.shadowRoot.getElementById("form-error");
    error.textContent = "";
    let scheduledAt = null;
    let nextTrigger = null;
    let cronAnchor = null;
    try {
      if (this._editingId) {
        nextTrigger = this._parseDateTime(
          form.elements.next_trigger_date.value,
          form.elements.next_trigger_time.value,
        );
      }
      if (!this._editingId && type !== "cron") {
        scheduledAt = this._parseDateTime(
          form.elements.scheduled_date.value,
          form.elements.scheduled_time.value,
        );
      } else if (this._editingId && type !== "cron") {
        scheduledAt = this._editingReminder.reminder_type === type
          ? this._editingReminder.scheduled_at || nextTrigger
          : nextTrigger;
      }
      if (type === "cron" && form.elements.cron_anchor_date.value.trim()) {
        cronAnchor = this._parseDate(form.elements.cron_anchor_date.value);
      }
    } catch (exception) {
      error.textContent = this._errorMessage(exception);
      return;
    }
    const recipients = form.elements.recipient_ids.value
      .split(/[\n,]+/)
      .map((value) => value.trim())
      .filter(Boolean);
    const reminder = {
      id: this._editingId || form.elements.id.value.trim(),
      name: form.elements.name.value.trim(),
      enabled: form.elements.enabled.checked,
      reminder_type: type,
      scheduled_at: scheduledAt,
      cron: type === "cron" ? form.elements.cron.value.trim() : null,
      cron_anchor: cronAnchor,
      delay_minutes: type === "after_completion" ? Number(form.elements.delay_minutes.value) : null,
      ignore_dnd: form.elements.ignore_dnd.checked,
      repeat_interval_minutes: Number(form.elements.repeat_interval_minutes.value),
      default_snooze_minutes: Number(form.elements.default_snooze_minutes.value),
      first_text: form.elements.first_text.value.trim(),
      repeat_text: form.elements.repeat_text.value.trim(),
      snoozed_text: form.elements.snoozed_text.value.trim(),
      completed_text: form.elements.completed_text.value.trim(),
      recipient_ids: recipients,
    };
    if (
      this._editingId
      && (
        form.elements.next_trigger_date.value !== this._initialNextTrigger.date
        || form.elements.next_trigger_time.value !== this._initialNextTrigger.time
      )
    ) {
      reminder.next_trigger = nextTrigger;
    }
    const save = this.shadowRoot.getElementById("save");
    save.disabled = true;
    try {
      if (this._editingId) {
        await this._send("update", { reminder_id: this._editingId, reminder });
      } else {
        await this._send("create", { reminder });
      }
      this._closeEditor();
      await this._load();
    } catch (exception) {
      error.textContent = this._errorMessage(exception);
    } finally {
      save.disabled = false;
    }
  }

  _send(command, data) {
    return this._hass.connection.sendMessagePromise({ type: `smart_reminder/${command}`, ...data });
  }

  _generateReminderId() {
    const randomPart = globalThis.crypto && typeof globalThis.crypto.randomUUID === "function"
      ? globalThis.crypto.randomUUID().replace(/-/g, "").slice(0, 12)
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
    return `reminder_${randomPart}`;
  }

  _formatDate(value) {
    const parts = this._dateTimeParts(value);
    return parts
      ? `${parts.day}.${parts.month}.${parts.year}, ${parts.hour}:${parts.minute}`
      : "—";
  }

  _formatDateOnly(value) {
    const parts = this._dateTimeParts(value);
    return parts ? `${parts.day}.${parts.month}.${parts.year}` : "";
  }

  _formatForForm(value) {
    const parts = this._dateTimeParts(value);
    if (!parts) return { date: "", time: "" };
    return {
      date: `${parts.day}.${parts.month}.${parts.year}`,
      time: `${parts.hour}:${parts.minute}`,
    };
  }

  _dateTimeParts(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    try {
      const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone: this._settings.timezone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }).formatToParts(date).reduce((result, part) => {
        result[part.type] = part.value;
        return result;
      }, {});
      return parts;
    } catch (_) {
      const pad = (number) => String(number).padStart(2, "0");
      return {
        year: String(date.getFullYear()),
        month: pad(date.getMonth() + 1),
        day: pad(date.getDate()),
        hour: pad(date.getHours()),
        minute: pad(date.getMinutes()),
      };
    }
  }

  _parseDate(value) {
    const match = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value.trim());
    if (!match) throw new Error("Дата должна быть указана в формате ДД.ММ.ГГГГ");
    const [, day, month, year] = match;
    const validationDate = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
    if (
      validationDate.getUTCFullYear() !== Number(year)
      || validationDate.getUTCMonth() !== Number(month) - 1
      || validationDate.getUTCDate() !== Number(day)
    ) {
      throw new Error("Указана несуществующая календарная дата");
    }
    return `${year}-${month}-${day}`;
  }

  _parseDateTime(dateValue, timeValue) {
    const date = this._parseDate(dateValue);
    const time = timeValue.trim();
    if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(time)) {
      throw new Error("Время должно быть указано в 24-часовом формате ЧЧ:ММ");
    }
    return `${date}T${time}`;
  }

  _minutesToDuration(value) {
    let minutes = Number(value) || 1;
    const days = Math.floor(minutes / 1440);
    minutes %= 1440;
    const hours = Math.floor(minutes / 60);
    minutes %= 60;
    return `${days ? `${days}d` : ""}${hours ? `${hours}h` : ""}${minutes || (!days && !hours) ? `${minutes}m` : ""}`;
  }

  _showGlobalError(message) {
    const element = this.shadowRoot && this.shadowRoot.getElementById("global-error");
    if (!element) return;
    element.textContent = message;
    element.classList.toggle("visible", Boolean(message));
  }

  _errorMessage(error) {
    return error?.message || error?.error?.message || String(error || "Неизвестная ошибка");
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "'": "&#39;",
      '"': "&quot;",
    })[character]);
  }
}

if (!customElements.get("smart-reminder-panel")) {
  customElements.define("smart-reminder-panel", SmartReminderPanel);
}
