    const defaultBroadcast = String(window.defaultBroadcast || "");
    const toggleSetupBtn = document.getElementById("toggleSetupBtn");
    const globalStatus = document.getElementById("globalStatus");
    const devicesRoot = document.getElementById("devices");
    const passwordModal = document.getElementById("passwordModal");
    const passwordModalTitle = document.getElementById("passwordModalTitle");
    const passwordModalMessage = document.getElementById("passwordModalMessage");
    const passwordModalInput = document.getElementById("passwordModalInput");
    const passwordModalRemember = document.getElementById("passwordModalRemember");
    const passwordModalError = document.getElementById("passwordModalError");
    const passwordModalCancel = document.getElementById("passwordModalCancel");
    const passwordModalConfirm = document.getElementById("passwordModalConfirm");
    const changePasswordModal = document.getElementById("changePasswordModal");
    const changePasswordCurrent = document.getElementById("changePasswordCurrent");
    const changePasswordNew = document.getElementById("changePasswordNew");
    const changePasswordRepeat = document.getElementById("changePasswordRepeat");
    const changePasswordModalError = document.getElementById("changePasswordModalError");
    const changePasswordCancel = document.getElementById("changePasswordCancel");
    const changePasswordConfirm = document.getElementById("changePasswordConfirm");
    const confirmModal = document.getElementById("confirmModal");
    const confirmModalTitle = document.getElementById("confirmModalTitle");
    const confirmModalMessage = document.getElementById("confirmModalMessage");
    const confirmModalCancel = document.getElementById("confirmModalCancel");
    const confirmModalConfirm = document.getElementById("confirmModalConfirm");
    const COOKIE_UNLOCK_SENTINEL = "__cookie_unlock__";
    const state = { devices: [], unlockedPasswords: {}, draftDevice: null, lastRememberChoice: true };

    // --- Cookie-based device order ---
    function getCookieOrder() {
      const match = document.cookie.split('; ').find(row => row.startsWith('device_order='));
      if (!match) return [];
      try { return JSON.parse(decodeURIComponent(match.split('=').slice(1).join('='))); } catch { return []; }
    }

    function saveCookieOrder(ids) {
      const value = encodeURIComponent(JSON.stringify(ids));
      document.cookie = 'device_order=' + value + '; path=/; max-age=' + (60 * 60 * 24 * 365) + '; SameSite=Lax';
    }

    function applyDeviceOrder() {
      const order = getCookieOrder();
      if (!order.length) return;
      const orderMap = new Map(order.map((id, i) => [id, i]));
      state.devices.sort((a, b) => {
        const ia = orderMap.has(a.id) ? orderMap.get(a.id) : Infinity;
        const ib = orderMap.has(b.id) ? orderMap.get(b.id) : Infinity;
        return ia - ib;
      });
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function setGlobalStatus(type, message) {
      globalStatus.className = "";
      if (type) {
        globalStatus.classList.add("status-" + type);
      }
      globalStatus.textContent = message || "";
    }

    function updateBodyScrollLock() {
      const modalOpen = !passwordModal.hidden || !changePasswordModal.hidden || !confirmModal.hidden;
      document.body.style.overflow = modalOpen ? "hidden" : "";
    }

    function showModal(modal) {
      modal.hidden = false;
      updateBodyScrollLock();
    }

    function hideModal(modal) {
      modal.hidden = true;
      updateBodyScrollLock();
    }

    function pruneUnlockedPasswords() {
      const validIds = new Set(state.devices.map((device) => device.id));
      Object.keys(state.unlockedPasswords).forEach((deviceId) => {
        if (!validIds.has(deviceId)) {
          delete state.unlockedPasswords[deviceId];
        }
      });
    }

    function openPasswordDialog(options) {
      const title = options?.title || "Password Required";
      const message = options?.message || "Enter password to continue.";
      const confirmLabel = options?.confirmLabel || "Continue";

      passwordModalTitle.textContent = title;
      passwordModalMessage.textContent = message;
      passwordModalConfirm.textContent = confirmLabel;
      passwordModalInput.value = "";
      const hideRemember = !!options?.hideRemember;
      const rememberLabel = passwordModalRemember.closest("label");
      if (rememberLabel) {
        rememberLabel.hidden = hideRemember;
      }
      passwordModalRemember.checked = hideRemember ? false : (options?.rememberChecked === undefined ? true : !!options.rememberChecked);
      passwordModalError.textContent = "";
      showModal(passwordModal);

      return new Promise((resolve) => {
        let settled = false;

        const cleanup = () => {
          passwordModalCancel.removeEventListener("click", onCancel);
          passwordModalConfirm.removeEventListener("click", onConfirm);
          passwordModalInput.removeEventListener("keydown", onKeyDown);
          hideModal(passwordModal);
        };

        const finish = (value) => {
          if (settled) {
            return;
          }
          settled = true;
          cleanup();
          resolve(value);
        };

        const onCancel = () => finish(null);

        const onConfirm = () => {
          const value = passwordModalInput.value;
          if (!value) {
            passwordModalError.textContent = "Password is required.";
            passwordModalInput.focus();
            return;
          }
          if (!hideRemember) {
            state.lastRememberChoice = passwordModalRemember.checked;
          }
          finish({
            password: value,
            rememberPassword: hideRemember ? false : passwordModalRemember.checked,
          });
        };

        const onKeyDown = (event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
            return;
          }
          if (event.key === "Enter") {
            event.preventDefault();
            onConfirm();
          }
        };

        passwordModalCancel.addEventListener("click", onCancel);
        passwordModalConfirm.addEventListener("click", onConfirm);
        passwordModalInput.addEventListener("keydown", onKeyDown);
        passwordModalInput.focus();
      });
    }

    function openConfirmDialog(options) {
      const title = options?.title || "Please Confirm";
      const message = options?.message || "Continue?";
      const confirmLabel = options?.confirmLabel || "Confirm";

      confirmModalTitle.textContent = title;
      confirmModalMessage.textContent = message;
      confirmModalConfirm.textContent = confirmLabel;
      showModal(confirmModal);

      return new Promise((resolve) => {
        let settled = false;

        const cleanup = () => {
          confirmModalCancel.removeEventListener("click", onCancel);
          confirmModalConfirm.removeEventListener("click", onConfirm);
          document.removeEventListener("keydown", onKeyDown, true);
          hideModal(confirmModal);
        };

        const finish = (value) => {
          if (settled) {
            return;
          }
          settled = true;
          cleanup();
          resolve(value);
        };

        const onCancel = () => finish(false);
        const onConfirm = () => finish(true);
        const onKeyDown = (event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
          }
        };

        confirmModalCancel.addEventListener("click", onCancel);
        confirmModalConfirm.addEventListener("click", onConfirm);
        document.addEventListener("keydown", onKeyDown, true);
        confirmModalConfirm.focus();
      });
    }

    function openChangePasswordDialog(requireCurrent = false) {
      const currentPasswordField = changePasswordCurrent.closest(".field");
      if (currentPasswordField) {
        currentPasswordField.hidden = !requireCurrent;
      }

      changePasswordCurrent.disabled = !requireCurrent;
      changePasswordCurrent.value = "";
      changePasswordCurrent.placeholder = requireCurrent ? "Current password" : "Not required while device is unlocked";
      changePasswordNew.value = "";
      changePasswordRepeat.value = "";
      changePasswordModalError.textContent = "";
      showModal(changePasswordModal);

      return new Promise((resolve) => {
        let settled = false;

        const cleanup = () => {
          changePasswordCancel.removeEventListener("click", onCancel);
          changePasswordConfirm.removeEventListener("click", onConfirm);
          changePasswordCurrent.removeEventListener("keydown", onKeyDown);
          changePasswordNew.removeEventListener("keydown", onKeyDown);
          changePasswordRepeat.removeEventListener("keydown", onKeyDown);
          hideModal(changePasswordModal);
        };

        const finish = (value) => {
          if (settled) {
            return;
          }
          settled = true;
          cleanup();
          resolve(value);
        };

        const onCancel = () => finish(null);

        const onConfirm = () => {
          const currentPassword = changePasswordCurrent.value;
          const newPassword = changePasswordNew.value;
          const repeatPassword = changePasswordRepeat.value;

          if (requireCurrent && !currentPassword) {
            changePasswordModalError.textContent = "Current password is required.";
            changePasswordCurrent.focus();
            return;
          }

          if (!newPassword || !newPassword.trim()) {
            changePasswordModalError.textContent = "New password is required.";
            changePasswordNew.focus();
            return;
          }

          if (!repeatPassword || !repeatPassword.trim()) {
            changePasswordModalError.textContent = "Confirm the new password.";
            changePasswordRepeat.focus();
            return;
          }

          if (newPassword !== repeatPassword) {
            changePasswordModalError.textContent = "New passwords do not match.";
            changePasswordRepeat.focus();
            return;
          }

          finish({ currentPassword, newPassword });
        };

        const onKeyDown = (event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
            return;
          }
          if (event.key === "Enter") {
            event.preventDefault();
            onConfirm();
          }
        };

        changePasswordCancel.addEventListener("click", onCancel);
        changePasswordConfirm.addEventListener("click", onConfirm);
        changePasswordCurrent.addEventListener("keydown", onKeyDown);
        changePasswordNew.addEventListener("keydown", onKeyDown);
        changePasswordRepeat.addEventListener("keydown", onKeyDown);

        if (requireCurrent) {
          changePasswordCurrent.focus();
        } else {
          changePasswordNew.focus();
        }
      });
    }

    function getDeviceById(deviceId) {
      return state.devices.find((device) => device.id === deviceId) || null;
    }

    function setRowStatus(row, type, message) {
      const status = row.querySelector(".row-status");
      if (!status) {
        return;
      }

      status.className = "row-status";
      if (type) {
        status.classList.add("status-" + type);
      }
      status.textContent = message || "";
    }

    function setAddDraftMode(isOpen) {
      toggleSetupBtn.textContent = isOpen ? "Cancel New Device" : "Add Device";
      toggleSetupBtn.setAttribute("aria-pressed", isOpen ? "true" : "false");
    }

    function displayName(device) {
      if (device.name) {
        return device.name;
      }
      if (device.has_password) {
        return "Locked Device";
      }
      return device.mac_address || "Unnamed Device";
    }

    function createDraftDevice() {
      return {
        id: "draft-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8),
        name: "",
        mac_address: "",
        address: "",
        broadcast_ip: defaultBroadcast,
        password: "",
        lock_wake_with_password: true,
        lock_ping_with_password: true
      };
    }

    function applyPasswordUi(row, hasPassword) {
      const passwordActionRow = row.querySelector('[data-role="password-action-row"]');
      const changePasswordButton = row.querySelector('button[data-action="change-password"]');
      const removePasswordButton = row.querySelector('button[data-action="remove-password"]');
      const lockOptionsField = row.querySelector('[data-role="lock-options"]');

      if (passwordActionRow) {
        passwordActionRow.classList.toggle("single-action", !hasPassword);
      }
      if (changePasswordButton) {
        changePasswordButton.textContent = hasPassword ? "Change Password" : "Add Password";
      }
      if (removePasswordButton) {
        removePasswordButton.hidden = !hasPassword;
      }
      if (lockOptionsField) {
        lockOptionsField.hidden = !hasPassword;
      }

      row.dataset.hasPassword = hasPassword ? "true" : "false";
    }

    function applyDraftPasswordUi(row) {
      if (!row || row.dataset.draft !== "true") {
        return;
      }

      const draftHasPassword = !!(state.draftDevice?.password || "").trim();
      const lockOptionsField = row.querySelector('[data-role="lock-options"]');
      const wasHidden = !!lockOptionsField?.hidden;
      applyPasswordUi(row, draftHasPassword);

      if (!lockOptionsField) {
        return;
      }

      const wakeCheckbox = row.querySelector('[data-field="lock_wake_with_password"]');
      const pingCheckbox = row.querySelector('[data-field="lock_ping_with_password"]');

      if (!draftHasPassword) {
        if (wakeCheckbox) {
          wakeCheckbox.checked = false;
        }
        if (pingCheckbox) {
          pingCheckbox.checked = false;
        }
      } else if (wasHidden) {
        if (wakeCheckbox) {
          wakeCheckbox.checked = true;
        }
        if (pingCheckbox) {
          pingCheckbox.checked = true;
        }
      }
    }

    function jsonOptions(method, body) {
      if (!body || Object.keys(body).length === 0) {
        return { method };
      }
      return {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      };
    }

    function isPasswordRequiredError(error) {
      return !!error && Number(error.status || 0) === 401;
    }

    async function runRememberableAuthRequest(requestFactory, passwordDialogOptions) {
      try {
        const payload = await requestFactory({});
        return { payload, canceled: false, credential: null };
      } catch (error) {
        if (!isPasswordRequiredError(error)) {
          throw error;
        }
      }

      const credential = await openPasswordDialog({
        ...(passwordDialogOptions || {}),
        rememberChecked: state.lastRememberChoice,
      });
      if (!credential) {
        return { payload: null, canceled: true, credential: null };
      }

      const body = { password: credential.password };
      if (credential.rememberPassword) {
        body.remember_password = true;
      }

      const payload = await requestFactory(body);
      return { payload, canceled: false, credential };
    }

    function populateEditFields(row, detail) {
      row.querySelector('[data-field="name"]').value = detail.name || "";
      row.querySelector('[data-field="mac_address"]').value = detail.mac_address || "";
      row.querySelector('[data-field="address"]').value = detail.address || "";
      row.querySelector('[data-field="broadcast_ip"]').value = detail.broadcast_ip || defaultBroadcast;
      row.querySelector('[data-field="lock_wake_with_password"]').checked = !!detail.lock_wake_with_password;
      row.querySelector('[data-field="lock_ping_with_password"]').checked = !!detail.lock_ping_with_password;

      applyPasswordUi(row, !!detail.has_password);
    }

    function buildEditSectionMarkup(options = {}) {
      const values = options.values || {};
      const hasPassword = !!options.hasPassword;
      const lockWakeWithPassword = !!options.lockWakeWithPassword;
      const lockPingWithPassword = !!options.lockPingWithPassword;
      const passwordActionLabel = hasPassword ? "Change Password" : "Add Password";
      const deleteButtonAttrs = options.disableDelete
        ? ' disabled title="Device has not been created yet."'
        : "";

      return `
        <div class="device-edit">
          <div class="edit-grid">
            <div class="field">
              <label>Name (option)</label>
              <input type="text" data-field="name" placeholder="Office PC" value="${escapeHtml(values.name || "")}">
            </div>
            <div class="field">
              <label>MAC Address</label>
              <input type="text" data-field="mac_address" placeholder="AA:BB:CC:DD:EE:FF" value="${escapeHtml(values.mac_address || "")}">
            </div>
            <div class="field">
              <label>Direct Address (option)</label>
              <input type="text" data-field="address" placeholder="Hostname or IP address" value="${escapeHtml(values.address || "")}">
            </div>
            <div class="field">
              <label>Broadcast IP</label>
              <input type="text" data-field="broadcast_ip" placeholder="${defaultBroadcast}" value="${escapeHtml(values.broadcast_ip || defaultBroadcast)}">
            </div>
            <div class="field lock-options-box" data-role="lock-options" ${hasPassword ? "" : "hidden"}>
              <label>Password Lock Options</label>
              <div class="lock-options-row lock-options-split">
                <div class="lock-option-item">
                  <label class="checkline"><input type="checkbox" data-field="lock_wake_with_password" ${lockWakeWithPassword ? "checked" : ""}>Require password for Wake</label>
                </div>
                <div class="lock-option-item">
                  <label class="checkline"><input type="checkbox" data-field="lock_ping_with_password" ${lockPingWithPassword ? "checked" : ""}>Require password for Ping</label>
                </div>
              </div>
            </div>
          </div>
          <div class="device-actions-edit">
            <div class="edit-actions-row edit-actions-row-top ${hasPassword ? "" : "single-action"}" data-role="password-action-row">
              <button type="button" data-action="change-password" class="ghost-btn">${passwordActionLabel}</button>
              <button type="button" data-action="remove-password" class="ghost-btn" ${hasPassword ? "" : "hidden"}>Remove Password</button>
            </div>
            <div class="edit-actions-row edit-actions-row-bottom">
              <button type="button" data-action="delete" class="ghost-btn"${deleteButtonAttrs}>Delete</button>
              <button type="button" data-action="cancel-edit" class="ghost-btn">Cancel</button>
              <button type="button" data-action="save">Save</button>
            </div>
          </div>
        </div>
      `;
    }

    function renderDraftDeviceCard() {
      const draft = state.draftDevice;
      if (!draft) {
        return null;
      }

      const draftHasPassword = !!(draft.password || "").trim();

      const card = document.createElement("article");
      card.className = "device";
      card.dataset.deviceId = draft.id;
      card.dataset.draft = "true";
      card.dataset.editing = "true";
      card.dataset.hasPassword = draftHasPassword ? "true" : "false";

      card.innerHTML = `
        <div class="device-view">
          <div class="device-top">
            <div>
              <h3>New Device</h3>
              <small>Fill out details and save to create this device.</small>
            </div>
          </div>
        </div>
        ${buildEditSectionMarkup({
          values: {
            name: draft.name,
            mac_address: draft.mac_address,
            address: draft.address,
            broadcast_ip: draft.broadcast_ip,
          },
          hasPassword: draftHasPassword,
          lockWakeWithPassword: draft.lock_wake_with_password,
          lockPingWithPassword: draft.lock_ping_with_password,
          disableDelete: true,
        })}
        <div class="row-status"></div>
      `;

      return card;
    }

    function renderDevices() {
      const total = state.devices.length;
      const hasDraft = !!state.draftDevice;
      devicesRoot.innerHTML = "";

      if (total === 0 && !hasDraft) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "No devices yet. Click Add Device to create your first one.";
        devicesRoot.appendChild(empty);
        return;
      }

      for (const device of state.devices) {
        const card = document.createElement("article");
        card.className = "device";
        card.dataset.deviceId = device.id;
        card.dataset.hasPassword = device.has_password ? "true" : "false";
        card.draggable = true;

        const label = escapeHtml(displayName(device));
        const mac = escapeHtml(device.mac_address || "");
        const broadcast = escapeHtml(device.broadcast_ip || defaultBroadcast);
        const macDisplay = device.has_password ? "Hidden" : mac;
        const broadcastDisplay = device.has_password ? "Hidden" : broadcast;
        const hasDirectAddress = (typeof device.has_direct_address === "boolean")
          ? device.has_direct_address
          : !!String(device.address || "").trim();
        const wakeLocked = device.has_password && !!device.lock_wake_with_password;
        const pingLocked = device.has_password && !!device.lock_ping_with_password;
        const editLocked = device.has_password;
        const lockIcon = '<span class="action-lock-icon" aria-hidden="true">&#128274;</span>';
        const wakeActionLabel = wakeLocked ? `${lockIcon}Wake` : "Wake";
        const pingActionLabel = pingLocked ? `${lockIcon}Ping` : "Ping";
        const editActionLabel = editLocked ? `${lockIcon}Edit` : "Edit";
        const pingActionHtml = hasDirectAddress
          ? `<button type="button" data-action="ping">${pingActionLabel}</button>`
          : "";
        const actionMainClass = hasDirectAddress
          ? "device-actions device-actions-main"
          : "device-actions device-actions-main two-actions";

        card.innerHTML = `
          <div class="device-view">
            <div class="device-top">
              <div>
                <h3>${label}</h3>
              </div>
            </div>
            <div class="device-meta">
              <div>MAC:<strong>${macDisplay}</strong></div>
              <div>Broadcast:<strong>${broadcastDisplay}</strong></div>
            </div>
          </div>
          ${buildEditSectionMarkup({ hasPassword: device.has_password })}
          <div class="${actionMainClass}">
            <button type="button" data-action="wake">${wakeActionLabel}</button>
            ${pingActionHtml}
            <button type="button" data-action="edit">${editActionLabel}</button>
          </div>
          <div class="row-status"></div>
        `;

        devicesRoot.appendChild(card);
      }

      if (hasDraft) {
        const draftCard = renderDraftDeviceCard();
        if (draftCard) {
          devicesRoot.appendChild(draftCard);
        }
      }
    }

    function collectRowPayload(row) {
      const payload = {};
      const fields = row.querySelectorAll("[data-field]");
      fields.forEach((input) => {
        if (input.type === "checkbox") {
          payload[input.dataset.field] = input.checked;
        } else {
          payload[input.dataset.field] = input.value.trim();
        }
      });
      return payload;
    }

    function setRowEditing(row, editing) {
      row.dataset.editing = editing ? "true" : "false";
      if (!editing) {
        setRowStatus(row, "", "");
      }
    }

    async function api(path, options) {
      const response = await fetch(path, options || {});
      let payload = {};

      try {
        payload = await response.json();
      } catch (_) {
        payload = {};
      }

      if (!response.ok) {
        const error = new Error(payload.error || "Request failed");
        error.status = response.status;
        throw error;
      }

      return payload;
    }

    async function loadDevices() {
      const payload = await api("/api/devices");
      state.devices = payload.devices || [];
      applyDeviceOrder();
      pruneUnlockedPasswords();
      renderDevices();
    }

    async function reopenDeviceEditAfterRefresh(deviceId) {
      const device = getDeviceById(deviceId);
      if (!device) {
        return false;
      }

      const row = devicesRoot.querySelector('.device[data-device-id="' + deviceId + '"]');
      if (!row) {
        return false;
      }

      const detailsBody = {};
      if (device.has_password) {
        const unlockedPassword = state.unlockedPasswords[deviceId] || "";
        if (!unlockedPassword) {
          return false;
        }
        if (unlockedPassword !== COOKIE_UNLOCK_SENTINEL) {
          detailsBody.password = unlockedPassword;
        }
      }

      try {
        const detailPayload = await api(
          "/api/devices/" + deviceId + "/details",
          jsonOptions("POST", detailsBody)
        );
        populateEditFields(row, detailPayload.device || {});
        setRowEditing(row, true);
        setRowStatus(row, "", "");
        return true;
      } catch (_) {
        return false;
      }
    }

    function cancelDraftEditor(message = "New device draft canceled.") {
      state.draftDevice = null;
      renderDevices();
      setAddDraftMode(false);
      if (message) {
        setGlobalStatus("", message);
      }
    }

    async function handlePasswordChangeForRow(row, options) {
      const context = options || {};
      const hasPassword = row.dataset.hasPassword === "true";
      const change = await openChangePasswordDialog(hasPassword);
      if (!change) {
        setRowStatus(row, "warning", "Password change canceled.");
        return;
      }

      if (context.isDraft) {
        if (!state.draftDevice) {
          throw new Error("Draft device is no longer available.");
        }
        state.draftDevice.password = change.newPassword;
        state.draftDevice.lock_wake_with_password = true;
        state.draftDevice.lock_ping_with_password = true;
        applyDraftPasswordUi(row);
        setRowStatus(row, "success", "Draft password updated.");
        return;
      }

      const body = { new_password: change.newPassword };
      if (hasPassword) {
        body.current_password = change.currentPassword;
        body.password = change.currentPassword;
      }

      await api("/api/devices/" + context.deviceId, jsonOptions("PUT", body));
      state.unlockedPasswords[context.deviceId] = change.newPassword;
      await loadDevices();
      const reopened = await reopenDeviceEditAfterRefresh(context.deviceId);
      if (reopened) {
        setGlobalStatus("success", "Device password updated.");
      } else {
        setGlobalStatus("warning", "Device password updated. Re-open edit to continue.");
      }
    }

    async function handlePasswordRemoveForRow(row, options) {
      const context = options || {};
      if (row.dataset.hasPassword !== "true") {
        const message = context.isDraft ? "This draft has no password set." : "This device has no password set.";
        setRowStatus(row, "warning", message);
        return;
      }

      if (context.isDraft) {
        if (!state.draftDevice) {
          throw new Error("Draft device is no longer available.");
        }
        state.draftDevice.password = "";
        state.draftDevice.lock_wake_with_password = false;
        state.draftDevice.lock_ping_with_password = false;
        applyDraftPasswordUi(row);
        setRowStatus(row, "success", "Draft password removed.");
        return;
      }

      const credential = await openPasswordDialog({
        title: "Remove Device Password",
        message: "Enter current password to remove password protection.",
        confirmLabel: "Remove Password",
        hideRemember: true,
      });
      if (!credential) {
        setRowStatus(row, "warning", "Password removal canceled.");
        return;
      }

      const body = {
        password: credential.password,
        current_password: credential.password,
      };

      await api(
        "/api/devices/" + context.deviceId + "/password",
        jsonOptions("DELETE", body)
      );
      delete state.unlockedPasswords[context.deviceId];
      await loadDevices();
      const reopened = await reopenDeviceEditAfterRefresh(context.deviceId);
      if (reopened) {
        setGlobalStatus("success", "Password removed for this device.");
      } else {
        setGlobalStatus("warning", "Password removed. Re-open edit to continue.");
      }
    }

    async function handleSaveForRow(row, options) {
      const context = options || {};
      const body = collectRowPayload(row);

      if (context.isDraft) {
        body.password = (state.draftDevice?.password || "").toString().trim();
        if (!body.password) {
          body.lock_wake_with_password = false;
          body.lock_ping_with_password = false;
        }

        if (!body.mac_address) {
          throw new Error("MAC address is required.");
        }

        await api("/api/devices", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        });

        state.draftDevice = null;
        await loadDevices();
        setAddDraftMode(false);
        setGlobalStatus("success", "Device added.");
        return;
      }

      if (context.device?.has_password) {
        const unlockedPassword = state.unlockedPasswords[context.deviceId] || "";
        if (!unlockedPassword) {
          throw new Error("Unlock expired. Re-open edit to save changes.");
        }
        if (unlockedPassword !== COOKIE_UNLOCK_SENTINEL) {
          body.password = unlockedPassword;
        }
      }

      if (!body.mac_address) {
        throw new Error("MAC address is required.");
      }

      await api("/api/devices/" + context.deviceId, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      await loadDevices();
      setGlobalStatus("success", "Device updated.");
    }

    toggleSetupBtn.addEventListener("click", () => {
      if (state.draftDevice) {
        cancelDraftEditor();
        return;
      }

      state.draftDevice = createDraftDevice();
      renderDevices();
      setAddDraftMode(true);
      setGlobalStatus("", "New device draft ready.");

      const draftRow = devicesRoot.querySelector('.device[data-draft="true"]');
      applyDraftPasswordUi(draftRow);
      const firstInput = draftRow?.querySelector('input[data-field="name"]');
      if (firstInput) {
        firstInput.focus();
      }
    });

    devicesRoot.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) {
        return;
      }

      const row = event.target.closest(".device");
      if (!row) {
        return;
      }

      const isDraft = row.dataset.draft === "true";
      const deviceId = row.dataset.deviceId;
      const action = button.dataset.action;
      if (!action || (!isDraft && !deviceId)) {
        return;
      }

      if (isDraft) {
        if (action === "cancel-edit") {
          cancelDraftEditor();
          return;
        }

        if (action === "change-password") {
          await handlePasswordChangeForRow(row, { isDraft: true });
          return;
        }

        if (action === "remove-password") {
          await handlePasswordRemoveForRow(row, { isDraft: true });
          return;
        }

        if (action !== "save") {
          return;
        }

        const buttons = row.querySelectorAll("button");
        buttons.forEach((item) => {
          item.disabled = true;
        });
        setRowStatus(row, "", "Creating device...");

        try {
          await handleSaveForRow(row, { isDraft: true });
        } catch (error) {
          setRowStatus(row, "error", error.message || "Failed to add device.");
        } finally {
          buttons.forEach((item) => {
            item.disabled = false;
          });
        }
        return;
      }

      const device = getDeviceById(deviceId);
      if (!device) {
        setRowStatus(row, "error", "Device data is out of date. Refreshing...");
        await loadDevices();
        return;
      }

      if (action === "edit") {
        const buttons = row.querySelectorAll("button");
        buttons.forEach((item) => {
          item.disabled = true;
        });

        try {
          setRowStatus(row, "", "Unlocking edit...");
          let detailPayload = null;
          if (device.has_password) {
            const result = await runRememberableAuthRequest(
              (body) => api(
                "/api/devices/" + deviceId + "/details",
                jsonOptions("POST", body)
              ),
              {
                title: "Unlock Device Settings",
                message: "Enter this device password to open settings.",
                confirmLabel: "Unlock"
              }
            );
            if (result.canceled) {
              setRowStatus(row, "warning", "Edit canceled.");
              return;
            }
            detailPayload = result.payload;
            if (result.credential?.password) {
              state.unlockedPasswords[deviceId] = result.credential.password;
            } else {
              state.unlockedPasswords[deviceId] = COOKIE_UNLOCK_SENTINEL;
            }
          } else {
            detailPayload = await api(
              "/api/devices/" + deviceId + "/details",
              jsonOptions("POST", {})
            );
          }

          populateEditFields(row, detailPayload.device || {});
          setRowEditing(row, true);
          setRowStatus(row, "", "");
        } catch (error) {
          setRowStatus(row, "error", error.message || "Failed to open edit mode.");
        } finally {
          buttons.forEach((item) => {
            item.disabled = false;
          });
        }
        return;
      }

      if (action === "cancel-edit") {
        delete state.unlockedPasswords[deviceId];
        renderDevices();
        return;
      }

      if (action === "delete") {
        const confirmed = await openConfirmDialog({
          title: "Delete Device",
          message: "Delete this device? This cannot be undone.",
          confirmLabel: "Delete"
        });
        if (!confirmed) {
          return;
        }
      }

      const buttons = row.querySelectorAll("button");
      buttons.forEach((item) => {
        item.disabled = true;
      });
      setRowStatus(row, "", "Working...");

      try {
        if (action === "wake") {
          let body = {};
          if (device.has_password && device.lock_wake_with_password) {
            const result = await runRememberableAuthRequest(
              (requestBody) => api(
                "/api/devices/" + deviceId + "/wake",
                jsonOptions("POST", requestBody)
              ),
              {
                title: "Wake Password",
                message: "Enter password to send Wake command.",
                confirmLabel: "Send Wake"
              }
            );
            if (result.canceled) {
              setRowStatus(row, "warning", "Wake canceled.");
              return;
            }
            const payload = result.payload;
            setRowStatus(row, "success", payload.message || "Wake packet sent.");
            return;
          }

          const payload = await api(
            "/api/devices/" + deviceId + "/wake",
            jsonOptions("POST", body)
          );
          setRowStatus(row, "success", payload.message || "Wake packet sent.");
        } else if (action === "ping") {
          let body = {};
          if (device.has_password && device.lock_ping_with_password) {
            const result = await runRememberableAuthRequest(
              (requestBody) => api(
                "/api/devices/" + deviceId + "/ping",
                jsonOptions("POST", requestBody)
              ),
              {
                title: "Ping Password",
                message: "Enter password to run Ping.",
                confirmLabel: "Run Ping"
              }
            );
            if (result.canceled) {
              setRowStatus(row, "warning", "Ping canceled.");
              return;
            }
            const payload = result.payload;
            if (payload.online) {
              setRowStatus(row, "success", "Ping successful.");
            } else {
              setRowStatus(row, "warning", "Ping failed.");
            }
            return;
          }

          const payload = await api(
            "/api/devices/" + deviceId + "/ping",
            jsonOptions("POST", body)
          );
          if (payload.online) {
            setRowStatus(row, "success", "Ping successful.");
          } else {
            setRowStatus(row, "warning", "Ping failed.");
          }
        } else if (action === "save") {
          await handleSaveForRow(row, { isDraft: false, deviceId, device });
        } else if (action === "change-password") {
          await handlePasswordChangeForRow(row, { isDraft: false, deviceId });
        } else if (action === "remove-password") {
          await handlePasswordRemoveForRow(row, { isDraft: false, deviceId });
        } else if (action === "delete") {
          const body = {};
          if (device.has_password) {
            const unlockedPassword = state.unlockedPasswords[deviceId] || "";
            if (!unlockedPassword) {
              throw new Error("Unlock expired. Re-open edit to delete device.");
            }
            if (unlockedPassword !== COOKIE_UNLOCK_SENTINEL) {
              body.password = unlockedPassword;
            }
          }

          await api("/api/devices/" + deviceId, jsonOptions("DELETE", body));
          delete state.unlockedPasswords[deviceId];
          await loadDevices();
          setGlobalStatus("success", "Device deleted.");
        }
      } catch (error) {
        setRowStatus(row, "error", error.message || "Action failed.");
      } finally {
        buttons.forEach((item) => {
          item.disabled = false;
        });
      }
    });

    // --- Drag-and-drop reordering ---
    let dragEnabled = false;
    let dragSrcId = null;

    devicesRoot.addEventListener('mousedown', (e) => {
      dragEnabled = !!e.target.closest('.device-view');
    });

    devicesRoot.addEventListener('dragstart', (e) => {
      const row = e.target.closest('.device');
      if (!dragEnabled || !row || row.dataset.draft === 'true' || row.dataset.editing === 'true') {
        e.preventDefault();
        return;
      }
      dragSrcId = row.dataset.deviceId;
      row.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', dragSrcId);
    });

    devicesRoot.addEventListener('dragend', () => {
      dragEnabled = false;
      dragSrcId = null;
      devicesRoot.querySelectorAll('.device').forEach(el => {
        el.classList.remove('dragging', 'drag-over-before', 'drag-over-after');
      });
    });

    devicesRoot.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      const target = e.target.closest('.device');
      if (!target || target.dataset.deviceId === dragSrcId || target.dataset.draft === 'true') return;
      devicesRoot.querySelectorAll('.device').forEach(el => {
        el.classList.remove('drag-over-before', 'drag-over-after');
      });
      const rect = target.getBoundingClientRect();
      if (e.clientY < rect.top + rect.height / 2) {
        target.classList.add('drag-over-before');
      } else {
        target.classList.add('drag-over-after');
      }
    });

    devicesRoot.addEventListener('dragleave', (e) => {
      const target = e.target.closest('.device');
      if (target) {
        target.classList.remove('drag-over-before', 'drag-over-after');
      }
    });

    devicesRoot.addEventListener('drop', (e) => {
      e.preventDefault();
      devicesRoot.querySelectorAll('.device').forEach(el => {
        el.classList.remove('drag-over-before', 'drag-over-after');
      });
      const targetRow = e.target.closest('.device');
      if (!dragSrcId || !targetRow || targetRow.dataset.draft === 'true') return;
      const targetId = targetRow.dataset.deviceId;
      if (!targetId || targetId === dragSrcId) return;

      const rect = targetRow.getBoundingClientRect();
      const insertBefore = e.clientY < rect.top + rect.height / 2;
      const srcIndex = state.devices.findIndex(d => d.id === dragSrcId);
      if (srcIndex === -1) return;
      const [moved] = state.devices.splice(srcIndex, 1);
      const newTgtIndex = state.devices.findIndex(d => d.id === targetId);
      if (newTgtIndex === -1) { state.devices.splice(srcIndex, 0, moved); return; }
      state.devices.splice(insertBefore ? newTgtIndex : newTgtIndex + 1, 0, moved);

      saveCookieOrder(state.devices.map(d => d.id));
      renderDevices();
    });

    // --- Touch drag-and-drop reordering (mobile) ---
    let touchSrcId = null;
    let touchSrcRow = null;
    let touchOverRow = null;
    let touchInsertBefore = false;
    let touchGhost = null;
    let touchOffsetX = 0;
    let touchOffsetY = 0;

    function clearTouchOverIndicators() {
      devicesRoot.querySelectorAll('.device').forEach(el => {
        el.classList.remove('drag-over-before', 'drag-over-after');
      });
    }

    function createTouchGhost(row, touch) {
      const rect = row.getBoundingClientRect();
      const clone = row.cloneNode(true);
      clone.className = 'device touch-ghost';
      clone.style.width = rect.width + 'px';
      clone.style.left = rect.left + 'px';
      clone.style.top = rect.top + window.scrollY + 'px';
      document.body.appendChild(clone);
      touchOffsetX = touch.clientX - rect.left;
      touchOffsetY = touch.clientY - rect.top;
      return clone;
    }

    function moveTouchGhost(touch) {
      if (!touchGhost) return;
      touchGhost.style.left = (touch.clientX - touchOffsetX) + 'px';
      touchGhost.style.top = (touch.clientY - touchOffsetY + window.scrollY) + 'px';
    }

    function removeTouchGhost() {
      if (touchGhost) { touchGhost.remove(); touchGhost = null; }
    }

    devicesRoot.addEventListener('touchstart', (e) => {
      const view = e.target.closest('.device-view');
      if (!view) return;
      const row = view.closest('.device');
      if (!row || row.dataset.draft === 'true' || row.dataset.editing === 'true') return;
      touchSrcId = row.dataset.deviceId;
      touchSrcRow = row;
      row.classList.add('dragging');
      touchGhost = createTouchGhost(row, e.touches[0]);
    }, { passive: true });

    devicesRoot.addEventListener('touchmove', (e) => {
      if (!touchSrcId) return;
      e.preventDefault();
      const touch = e.touches[0];
      moveTouchGhost(touch);
      // Hide ghost temporarily so elementFromPoint hits the card underneath
      if (touchGhost) touchGhost.style.display = 'none';
      const el = document.elementFromPoint(touch.clientX, touch.clientY);
      if (touchGhost) touchGhost.style.display = '';
      const target = el ? el.closest('.device') : null;
      clearTouchOverIndicators();
      if (!target || target.dataset.deviceId === touchSrcId || target.dataset.draft === 'true') {
        touchOverRow = null;
        return;
      }
      const rect = target.getBoundingClientRect();
      touchInsertBefore = touch.clientY < rect.top + rect.height / 2;
      touchOverRow = target;
      target.classList.add(touchInsertBefore ? 'drag-over-before' : 'drag-over-after');
    }, { passive: false });

    devicesRoot.addEventListener('touchend', () => {
      if (!touchSrcId) return;
      removeTouchGhost();
      clearTouchOverIndicators();
      if (touchSrcRow) touchSrcRow.classList.remove('dragging');

      if (touchOverRow) {
        const targetId = touchOverRow.dataset.deviceId;
        const srcIndex = state.devices.findIndex(d => d.id === touchSrcId);
        if (srcIndex !== -1 && targetId) {
          const [moved] = state.devices.splice(srcIndex, 1);
          const newTgtIndex = state.devices.findIndex(d => d.id === targetId);
          if (newTgtIndex !== -1) {
            state.devices.splice(touchInsertBefore ? newTgtIndex : newTgtIndex + 1, 0, moved);
            saveCookieOrder(state.devices.map(d => d.id));
            renderDevices();
          } else {
            state.devices.splice(srcIndex, 0, moved);
          }
        }
      }

      touchSrcId = null;
      touchSrcRow = null;
      touchOverRow = null;
    });

    devicesRoot.addEventListener('touchcancel', () => {
      removeTouchGhost();
      clearTouchOverIndicators();
      if (touchSrcRow) touchSrcRow.classList.remove('dragging');
      touchSrcId = null;
      touchSrcRow = null;
      touchOverRow = null;
    });

    loadDevices().catch((error) => {
      setGlobalStatus("error", error.message || "Failed to load devices.");
    });

    setAddDraftMode(false);
  