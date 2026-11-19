(() => {
  "use strict";

  const OPEN_MINUTES = 8 * 60;
  const CLOSE_MINUTES = 21 * 60;
  const TOTAL_MINUTES = CLOSE_MINUTES - OPEN_MINUTES; // 780 min (13 h)
  const SLOT_MINUTES = 30;
  const MAX_DURATION_MINUTES = 8 * 60;

  const state = {
    activeView: "spaces",
    allSpaces: [],
    spaces: [],
    bookings: [],
    scheduleData: null,
    availabilityData: null,
    availabilityReqSeq: 0,
    editingBooking: null,
  };

  /* ------------------------------------------------------------------ */
  /* Utilidades generales y seguridad XSS                               */
  /* ------------------------------------------------------------------ */

  function escapeHtml(value) {
    if (value === null || value === undefined) {
      return "";
    }
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatDateOffset(offsetDays = 0) {
    const dt = new Date();
    dt.setDate(dt.getDate() + offsetDays);
    const year = dt.getFullYear();
    const month = String(dt.getMonth() + 1).padStart(2, "0");
    const day = String(dt.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function formatCurrency(amount) {
    const num = Number(amount) || 0;
    return `${num.toFixed(2).replace(".", ",")} €`;
  }

  function formatHours(hours) {
    const num = Number(hours) || 0;
    return `${num.toFixed(1).replace(".", ",")} h`;
  }

  function hhmmToMinutes(hhmm) {
    if (!hhmm || typeof hhmm !== "string" || !hhmm.includes(":")) {
      return 0;
    }
    const [h, m] = hhmm.split(":").map(Number);
    return h * 60 + m;
  }

  function minutesToHhmm(totalMinutes) {
    const h = Math.floor(totalMinutes / 60);
    const m = totalMinutes % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  }

  function debounce(fn, delayMs) {
    let timerId = null;
    return (...args) => {
      window.clearTimeout(timerId);
      timerId = window.setTimeout(() => fn(...args), delayMs);
    };
  }

  function getStatusBadge(status) {
    const normalized = String(status || "").toLowerCase();
    if (normalized === "confirmada") {
      return { className: "badge-green", label: "Confirmada" };
    }
    if (normalized === "completada") {
      return { className: "badge-blue", label: "Completada" };
    }
    if (normalized === "cancelada") {
      return { className: "badge-red", label: "Cancelada" };
    }
    return { className: "badge-amber", label: status || "Desconocido" };
  }

  async function apiRequest(url, options = {}) {
    const config = {
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
      ...options,
    };

    const response = await fetch(url, config);
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await response.json()
      : {};

    if (!response.ok) {
      const error = new Error(
        data.error || `Error inesperado en el servidor (${response.status}).`
      );
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) {
      return;
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.setAttribute("role", "status");
    toast.innerHTML = `
      <span>${escapeHtml(message)}</span>
      <button type="button" class="toast-close" aria-label="Cerrar notificación">✕</button>
    `;

    const closeBtn = toast.querySelector(".toast-close");
    const removeToast = () => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    };

    if (closeBtn) {
      closeBtn.addEventListener("click", removeToast);
    }

    container.appendChild(toast);
    window.setTimeout(removeToast, 4200);
  }

  /* ------------------------------------------------------------------ */
  /* Referencias DOM                                                    */
  /* ------------------------------------------------------------------ */

  const dom = {
    tabs: Array.from(document.querySelectorAll(".tab-btn")),
    views: {
      spaces: document.getElementById("view-spaces"),
      schedule: document.getElementById("view-schedule"),
      bookings: document.getElementById("view-bookings"),
      analytics: document.getElementById("view-analytics"),
    },
    btnNewBooking: document.getElementById("btn-new-booking"),
    btnNewSpace: document.getElementById("btn-new-space"),
    btnExportCsv: document.getElementById("btn-export-csv"),

    // Espacios
    spacesFilterQ: document.getElementById("spaces-filter-q"),
    spacesFilterCategory: document.getElementById("spaces-filter-category"),
    spacesFilterCapacity: document.getElementById("spaces-filter-capacity"),
    spacesFilterActive: document.getElementById("spaces-filter-active"),
    spacesFilterReset: document.getElementById("spaces-filter-reset"),
    spacesCountLabel: document.getElementById("spaces-count-label"),
    spacesGrid: document.getElementById("spaces-grid"),
    spacesEmpty: document.getElementById("spaces-empty"),

    // Agenda diaria
    scheduleYesterday: document.getElementById("schedule-yesterday"),
    scheduleToday: document.getElementById("schedule-today"),
    scheduleTomorrow: document.getElementById("schedule-tomorrow"),
    scheduleDate: document.getElementById("schedule-date"),
    scheduleSummaryLabel: document.getElementById("schedule-summary-label"),
    scheduleBoard: document.getElementById("schedule-board"),
    scheduleEmpty: document.getElementById("schedule-empty"),

    // Reservas
    bookingsFilterQ: document.getElementById("bookings-filter-q"),
    bookingsFilterSpace: document.getElementById("bookings-filter-space"),
    bookingsFilterStatus: document.getElementById("bookings-filter-status"),
    bookingsFilterDate: document.getElementById("bookings-filter-date"),
    bookingsFilterReset: document.getElementById("bookings-filter-reset"),
    bookingsCountLabel: document.getElementById("bookings-count-label"),
    bookingsTbody: document.getElementById("bookings-tbody"),
    bookingsEmpty: document.getElementById("bookings-empty"),

    // Analítica
    analyticsDate: document.getElementById("analytics-date"),
    analyticsToday: document.getElementById("analytics-today"),
    kpiTotalRevenue: document.getElementById("kpi-total-revenue"),
    kpiTargetRevenue: document.getElementById("kpi-target-revenue"),
    kpiOccupancyToday: document.getElementById("kpi-occupancy-today"),
    kpiOccupancyBar: document.getElementById("kpi-occupancy-bar"),
    kpiHoursSummary: document.getElementById("kpi-hours-summary"),
    kpiCountConfirmada: document.getElementById("kpi-count-confirmada"),
    kpiActiveSpaces: document.getElementById("kpi-active-spaces"),
    kpiTotalBookings: document.getElementById("kpi-total-bookings"),
    kpiCountCompletada: document.getElementById("kpi-count-completada"),
    kpiCountCancelada: document.getElementById("kpi-count-cancelada"),
    analyticsBySpace: document.getElementById("analytics-by-space"),
    analyticsByHour: document.getElementById("analytics-by-hour"),

    // Modal Reserva
    bookingModal: document.getElementById("booking-modal"),
    bookingModalTitle: document.getElementById("booking-modal-title"),
    bookingModalRef: document.getElementById("booking-modal-ref"),
    bookingModalClose: document.getElementById("booking-modal-close"),
    bookingModalCancel: document.getElementById("booking-modal-cancel"),
    bookingForm: document.getElementById("booking-form"),
    bookingFormError: document.getElementById("booking-form-error"),
    bookingId: document.getElementById("booking-id"),
    bookingSpace: document.getElementById("booking-space"),
    bookingDate: document.getElementById("booking-date"),
    bookingStart: document.getElementById("booking-start"),
    bookingEnd: document.getElementById("booking-end"),
    availabilitySummary: document.getElementById("availability-summary"),
    availabilitySlots: document.getElementById("availability-slots"),
    bookingTitle: document.getElementById("booking-title"),
    bookingCustomerName: document.getElementById("booking-customer-name"),
    bookingCustomerEmail: document.getElementById("booking-customer-email"),
    bookingAttendees: document.getElementById("booking-attendees"),
    bookingCapacityHint: document.getElementById("booking-capacity-hint"),
    bookingNotes: document.getElementById("booking-notes"),
    bookingDurationPreview: document.getElementById("booking-duration-preview"),
    bookingRatePreview: document.getElementById("booking-rate-preview"),
    bookingPricePreview: document.getElementById("booking-price-preview"),
    bookingSubmitBtn: document.getElementById("booking-submit-btn"),

    // Modal Espacio
    spaceModal: document.getElementById("space-modal"),
    spaceModalClose: document.getElementById("space-modal-close"),
    spaceModalCancel: document.getElementById("space-modal-cancel"),
    spaceForm: document.getElementById("space-form"),
    spaceFormError: document.getElementById("space-form-error"),
    spaceName: document.getElementById("space-name"),
    spaceCategory: document.getElementById("space-category"),
    spaceFloor: document.getElementById("space-floor"),
    spaceCapacity: document.getElementById("space-capacity"),
    spaceHourlyRate: document.getElementById("space-hourly-rate"),
    spaceEquipment: document.getElementById("space-equipment"),
    spaceSubmitBtn: document.getElementById("space-submit-btn"),
  };

  /* ------------------------------------------------------------------ */
  /* Navegación por pestañas                                            */
  /* ------------------------------------------------------------------ */

  function switchView(viewName) {
    if (!dom.views[viewName]) {
      return;
    }
    state.activeView = viewName;

    dom.tabs.forEach((tab) => {
      const isSelected = tab.dataset.view === viewName;
      tab.classList.toggle("is-active", isSelected);
      tab.setAttribute("aria-selected", String(isSelected));
    });

    Object.entries(dom.views).forEach(([key, section]) => {
      section.hidden = key !== viewName;
    });

    refreshActiveView();
  }

  async function refreshActiveView() {
    try {
      if (state.activeView === "spaces") {
        await loadSpaces();
      } else if (state.activeView === "schedule") {
        await loadSchedule();
      } else if (state.activeView === "bookings") {
        await loadBookings();
      } else if (state.activeView === "analytics") {
        await loadAnalytics();
      }
    } catch (err) {
      showToast(err.message || "Error al actualizar la vista.", "error");
    }
  }

  /* ------------------------------------------------------------------ */
  /* Sincronización de catálogos de salas y selectores                  */
  /* ------------------------------------------------------------------ */

  async function loadAllSpacesCatalog() {
    const data = await apiRequest("/api/spaces");
    state.allSpaces = data.spaces || [];
    syncSpaceSelects();
  }

  function syncSpaceSelects() {
    const currentCategory = dom.spacesFilterCategory.value;
    const categories = Array.from(
      new Set(state.allSpaces.map((s) => s.category).filter(Boolean))
    ).sort((a, b) => a.localeCompare(b, "es"));

    dom.spacesFilterCategory.innerHTML = [
      '<option value="">Todas las categorías</option>',
      ...categories.map(
        (cat) =>
          `<option value="${escapeHtml(cat)}">${escapeHtml(cat)}</option>`
      ),
    ].join("");
    if (categories.includes(currentCategory)) {
      dom.spacesFilterCategory.value = currentCategory;
    }

    const currentBookingFilterSpace = dom.bookingsFilterSpace.value;
    dom.bookingsFilterSpace.innerHTML = [
      '<option value="">Todas las salas</option>',
      ...state.allSpaces.map(
        (space) =>
          `<option value="${escapeHtml(space.id)}">${escapeHtml(
            space.name
          )} (${escapeHtml(space.floor)})</option>`
      ),
    ].join("");
    if (currentBookingFilterSpace) {
      dom.bookingsFilterSpace.value = currentBookingFilterSpace;
    }

    const currentModalSpace = dom.bookingSpace.value;
    const activeSpaces = state.allSpaces.filter((s) => s.is_active);
    const modalSpaces = activeSpaces.length ? activeSpaces : state.allSpaces;
    dom.bookingSpace.innerHTML = modalSpaces
      .map(
        (space) =>
          `<option value="${escapeHtml(space.id)}">${escapeHtml(
            space.name
          )} · ${escapeHtml(space.capacity)} pax · ${escapeHtml(
            formatCurrency(space.hourly_rate)
          )}/h${space.is_active ? "" : " (Mantenimiento)"}</option>`
      )
      .join("");
    if (
      currentModalSpace &&
      modalSpaces.some((s) => String(s.id) === String(currentModalSpace))
    ) {
      dom.bookingSpace.value = currentModalSpace;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Vista 1: Espacios                                                  */
  /* ------------------------------------------------------------------ */

  function getSpacesFilterParams() {
    const params = new URLSearchParams();
    const q = dom.spacesFilterQ.value.trim();
    const category = dom.spacesFilterCategory.value.trim();
    const minCap = dom.spacesFilterCapacity.value.trim();
    const activeOnly = dom.spacesFilterActive.value.trim();

    if (q) {
      params.set("q", q);
    }
    if (category) {
      params.set("category", category);
    }
    if (minCap) {
      params.set("min_capacity", minCap);
    }
    if (activeOnly) {
      params.set("active_only", activeOnly);
    }
    return params;
  }

  async function loadSpaces() {
    const params = getSpacesFilterParams();
    const query = params.toString();
    const data = await apiRequest(`/api/spaces${query ? `?${query}` : ""}`);
    state.spaces = data.spaces || [];
    renderSpaces();
  }

  function renderSpaces() {
    const spaces = state.spaces;
    const activeCount = spaces.filter((s) => s.is_active).length;
    dom.spacesCountLabel.textContent = `${spaces.length} ${
      spaces.length === 1 ? "espacio mostrado" : "espacios mostrados"
    } (${activeCount} activos)`;

    if (spaces.length === 0) {
      dom.spacesGrid.innerHTML = "";
      dom.spacesEmpty.hidden = false;
      return;
    }

    dom.spacesEmpty.hidden = true;
    dom.spacesGrid.innerHTML = spaces
      .map((space) => {
        const statusBadge = space.is_active
          ? '<span class="badge badge-green">Activa</span>'
          : '<span class="badge badge-amber">Mantenimiento</span>';
        const equipmentItems = String(space.equipment || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
        const equipmentHtml = equipmentItems.length
          ? equipmentItems
              .map((item) => `<span class="tag">${escapeHtml(item)}</span>`)
              .join("")
          : '<span class="muted-text">Sin equipamiento registrado</span>';
        const toggleLabel = space.is_active
          ? "Poner en mantenimiento"
          : "Activar sala";

        return `
          <article class="card space-card${space.is_active ? "" : " is-inactive"}">
            <div class="space-card-top">
              <div>
                <h2 class="space-name">${escapeHtml(space.name)}</h2>
                <p class="space-meta">${escapeHtml(space.category)} · ${escapeHtml(
          space.floor
        )}</p>
              </div>
              ${statusBadge}
            </div>

            <div class="space-stats">
              <div>
                <span class="space-stat-label">Aforo máximo</span>
                <span class="space-stat-value">${escapeHtml(space.capacity)} personas</span>
              </div>
              <div>
                <span class="space-stat-label">Tarifa por hora</span>
                <span class="space-stat-value">${escapeHtml(
                  formatCurrency(space.hourly_rate)
                )}</span>
              </div>
            </div>

            <div class="tag-list">${equipmentHtml}</div>

            <div class="space-card-actions">
              <button
                type="button"
                class="btn btn-sm ${
                  space.is_active ? "btn-outline" : "btn-secondary"
                }"
                data-action="toggle-space"
                data-space-id="${escapeHtml(space.id)}"
                data-next-active="${space.is_active ? "false" : "true"}"
              >
                ${escapeHtml(toggleLabel)}
              </button>
              <button
                type="button"
                class="btn btn-sm btn-primary"
                data-action="book-space"
                data-space-id="${escapeHtml(space.id)}"
                ${space.is_active ? "" : "disabled"}
              >
                Reservar
              </button>
            </div>
          </article>
        `;
      })
      .join("");
  }

  async function toggleSpaceStatus(spaceId, nextActive) {
    try {
      const updated = await apiRequest(`/api/spaces/${spaceId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: nextActive }),
      });
      showToast(
        `${updated.name} marcada como ${
          updated.is_active ? "Activa" : "en Mantenimiento"
        }.`,
        "success"
      );
      await loadAllSpacesCatalog();
      await loadSpaces();
    } catch (err) {
      showToast(err.message || "No se pudo actualizar el estado.", "error");
    }
  }

  /* ------------------------------------------------------------------ */
  /* Vista 2: Agenda Diaria                                             */
  /* ------------------------------------------------------------------ */

  function syncScheduleDateButtons() {
    const selected = dom.scheduleDate.value;
    const targets = [
      [dom.scheduleYesterday, formatDateOffset(-1)],
      [dom.scheduleToday, formatDateOffset(0)],
      [dom.scheduleTomorrow, formatDateOffset(1)],
    ];
    targets.forEach(([btn, dateStr]) => {
      const isMatch = selected === dateStr;
      btn.classList.toggle("btn-secondary", isMatch);
      btn.classList.toggle("btn-outline", !isMatch);
    });
  }

  async function loadSchedule() {
    if (!dom.scheduleDate.value) {
      dom.scheduleDate.value = formatDateOffset(0);
    }
    syncScheduleDateButtons();
    const targetDate = dom.scheduleDate.value;
    const data = await apiRequest(
      `/api/schedule?date=${encodeURIComponent(targetDate)}`
    );
    state.scheduleData = data;
    renderSchedule();
  }

  function renderSchedule() {
    const data = state.scheduleData;
    const spaces = (data && data.spaces) || [];

    if (spaces.length === 0) {
      dom.scheduleBoard.innerHTML = "";
      dom.scheduleSummaryLabel.textContent = "";
      dom.scheduleEmpty.hidden = false;
      return;
    }

    dom.scheduleEmpty.hidden = true;
    const totalDayBookings = spaces.reduce(
      (acc, space) => acc + (space.bookings ? space.bookings.length : 0),
      0
    );
    dom.scheduleSummaryLabel.textContent = `${totalDayBookings} ${
      totalDayBookings === 1 ? "reserva activa" : "reservas activas"
    } el ${data.booking_date}`;

    const hourHeaders = [];
    for (let h = 8; h <= 20; h += 1) {
      hourHeaders.push(`<span>${String(h).padStart(2, "0")}:00</span>`);
    }

    const slotCellsTemplate = [];
    for (let m = OPEN_MINUTES; m < CLOSE_MINUTES; m += SLOT_MINUTES) {
      const slotStart = minutesToHhmm(m);
      const slotEnd = minutesToHhmm(m + SLOT_MINUTES);
      slotCellsTemplate.push({ start: slotStart, end: slotEnd });
    }

    const rowsHtml = spaces
      .map((space) => {
        const bgCellsHtml = slotCellsTemplate
          .map(
            (slot) => `
              <div
                class="timeline-slot-bg${space.is_active ? "" : " is-disabled"}"
                data-action="schedule-new"
                data-space-id="${escapeHtml(space.id)}"
                data-start="${escapeHtml(slot.start)}"
                data-end="${escapeHtml(slot.end)}"
                title="${
                  space.is_active
                    ? `Reservar ${escapeHtml(space.name)} desde ${escapeHtml(
                        slot.start
                      )}`
                    : "Sala en mantenimiento"
                }"
              ></div>
            `
          )
          .join("");

        const blocksHtml = (space.bookings || [])
          .map((booking) => {
            const startMin = hhmmToMinutes(booking.start_time);
            const endMin = hhmmToMinutes(booking.end_time);
            const leftPct = ((startMin - OPEN_MINUTES) / TOTAL_MINUTES) * 100;
            const widthPct = ((endMin - startMin) / TOTAL_MINUTES) * 100;
            const safeStatus =
              booking.status === "completada" ? "completada" : "confirmada";

            return `
              <button
                type="button"
                class="timeline-block status-${safeStatus}"
                style="left: ${leftPct.toFixed(4)}%; width: ${widthPct.toFixed(
              4
            )}%;"
                data-action="schedule-edit"
                data-booking-id="${escapeHtml(booking.id)}"
                title="${escapeHtml(booking.title)} (${escapeHtml(
              booking.start_time
            )}–${escapeHtml(booking.end_time)}) · ${escapeHtml(
              booking.customer_name
            )}"
              >
                <span>${escapeHtml(booking.start_time)}–${escapeHtml(
              booking.end_time
            )}</span>
                <span>${escapeHtml(booking.title)}</span>
              </button>
            `;
          })
          .join("");

        const inactiveTag = space.is_active
          ? ""
          : '<span class="badge badge-amber">Mantenimiento</span>';

        return `
          <div class="schedule-row">
            <div class="schedule-space-info">
              <div class="schedule-space-name">
                <span>${escapeHtml(space.name)}</span>
                ${inactiveTag}
              </div>
              <div class="schedule-space-sub">
                ${escapeHtml(space.floor)} · ${escapeHtml(
          space.capacity
        )} pax · ${escapeHtml(formatHours(space.booked_hours))} (${escapeHtml(
          space.occupancy_pct
        )}%)
              </div>
            </div>
            <div class="timeline-track">
              ${bgCellsHtml}
              ${blocksHtml}
            </div>
          </div>
        `;
      })
      .join("");

    dom.scheduleBoard.innerHTML = `
      <div class="schedule-header-row">
        <div class="field-label">Sala / Ocupación</div>
        <div class="schedule-hours-axis">${hourHeaders.join("")}</div>
      </div>
      ${rowsHtml}
    `;
  }

  function findBookingInSchedule(bookingId) {
    if (!state.scheduleData || !state.scheduleData.spaces) {
      return null;
    }
    for (const space of state.scheduleData.spaces) {
      const found = (space.bookings || []).find(
        (b) => Number(b.id) === Number(bookingId)
      );
      if (found) {
        return found;
      }
    }
    return null;
  }

  /* ------------------------------------------------------------------ */
  /* Vista 3: Reservas                                                  */
  /* ------------------------------------------------------------------ */

  function getBookingsFilterParams() {
    const params = new URLSearchParams();
    const q = dom.bookingsFilterQ.value.trim();
    const spaceId = dom.bookingsFilterSpace.value.trim();
    const status = dom.bookingsFilterStatus.value.trim();
    const dateVal = dom.bookingsFilterDate.value.trim();

    if (q) {
      params.set("q", q);
    }
    if (spaceId) {
      params.set("space_id", spaceId);
    }
    if (status) {
      params.set("status", status);
    }
    if (dateVal) {
      params.set("date", dateVal);
    }
    return params;
  }

  async function loadBookings() {
    const params = getBookingsFilterParams();
    const query = params.toString();
    const data = await apiRequest(`/api/bookings${query ? `?${query}` : ""}`);
    state.bookings = data.bookings || [];
    renderBookings();
  }

  function renderBookings() {
    const bookings = state.bookings;
    dom.bookingsCountLabel.textContent = `${bookings.length} ${
      bookings.length === 1 ? "reserva encontrada" : "reservas encontradas"
    }`;

    if (bookings.length === 0) {
      dom.bookingsTbody.innerHTML = "";
      dom.bookingsEmpty.hidden = false;
      return;
    }

    dom.bookingsEmpty.hidden = true;
    dom.bookingsTbody.innerHTML = bookings
      .map((booking) => {
        const badge = getStatusBadge(booking.status);
        const isCancelled = booking.status === "cancelada";
        const isConfirmed = booking.status === "confirmada";

        const completeBtn = isConfirmed
          ? `<button type="button" class="btn btn-sm btn-secondary" data-action="complete-booking" data-booking-id="${escapeHtml(
              booking.id
            )}">Completar</button>`
          : "";

        const cancelOrReactivateBtn = isCancelled
          ? `<button type="button" class="btn btn-sm btn-outline" data-action="reactivate-booking" data-booking-id="${escapeHtml(
              booking.id
            )}">Reactivar</button>`
          : `<button type="button" class="btn btn-sm btn-danger-outline" data-action="cancel-booking" data-booking-id="${escapeHtml(
              booking.id
            )}">Cancelar</button>`;

        return `
          <tr>
            <td>
              <span class="mono-code">${escapeHtml(booking.reference_code)}</span>
            </td>
            <td>
              <span class="cell-strong">${escapeHtml(booking.space_name)}</span>
              <span class="cell-sub">${escapeHtml(booking.space_floor)}</span>
            </td>
            <td>
              <span class="cell-strong">${escapeHtml(booking.booking_date)}</span>
              <span class="cell-sub">${escapeHtml(booking.start_time)} – ${escapeHtml(
          booking.end_time
        )} (${escapeHtml(formatHours(booking.duration_hours))})</span>
            </td>
            <td>
              <span class="cell-strong">${escapeHtml(booking.title)}</span>
              <span class="cell-sub">${escapeHtml(
                booking.customer_name
              )} · ${escapeHtml(booking.customer_email)}</span>
            </td>
            <td>${escapeHtml(booking.attendees)} / ${escapeHtml(
          booking.space_capacity
        )}</td>
            <td class="cell-strong">${escapeHtml(
              formatCurrency(booking.total_price)
            )}</td>
            <td>
              <span class="badge ${badge.className}">${escapeHtml(
          badge.label
        )}</span>
            </td>
            <td class="col-actions">
              <div class="row-actions">
                <button
                  type="button"
                  class="btn btn-sm btn-outline"
                  data-action="edit-booking"
                  data-booking-id="${escapeHtml(booking.id)}"
                  ${isCancelled ? "disabled title=\"No se pueden editar reservas canceladas\"" : ""}
                >
                  Editar
                </button>
                ${completeBtn}
                ${cancelOrReactivateBtn}
              </div>
            </td>
          </tr>
        `;
      })
      .join("");
  }

  async function changeBookingStatus(bookingId, status) {
    try {
      const updated = await apiRequest(`/api/bookings/${bookingId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      showToast(
        `Reserva ${updated.reference_code} actualizada a "${updated.status}".`,
        "success"
      );
      await loadBookings();
    } catch (err) {
      showToast(err.message || "No se pudo cambiar el estado.", "error");
    }
  }

  function exportBookingsCsv() {
    const params = getBookingsFilterParams();
    const query = params.toString();
    window.location.href = `/api/bookings/export${query ? `?${query}` : ""}`;
    showToast("Descarga CSV iniciada.", "info");
  }

  /* ------------------------------------------------------------------ */
  /* Vista 4: Analítica y gráficos SVG puros                            */
  /* ------------------------------------------------------------------ */

  async function loadAnalytics() {
    if (!dom.analyticsDate.value) {
      dom.analyticsDate.value = formatDateOffset(0);
    }
    const targetDate = dom.analyticsDate.value;
    const data = await apiRequest(
      `/api/analytics?date=${encodeURIComponent(targetDate)}`
    );
    renderAnalytics(data);
  }

  function renderAnalytics(data) {
    const counts = data.status_counts || {};
    dom.kpiTotalRevenue.textContent = formatCurrency(data.total_revenue);
    dom.kpiTargetRevenue.textContent = formatCurrency(data.target_date_revenue);

    const occupancyPct = Math.min(100, Math.max(0, Number(data.occupancy_today_pct) || 0));
    dom.kpiOccupancyToday.textContent = `${String(data.occupancy_today_pct || 0).replace(".", ",")}%`;
    dom.kpiOccupancyBar.style.width = `${occupancyPct}%`;
    dom.kpiHoursSummary.textContent = `${formatHours(
      data.total_hours
    )} acumuladas en ${data.active_bookings || 0} reservas activas`;

    dom.kpiCountConfirmada.textContent = String(counts.confirmada || 0);
    dom.kpiActiveSpaces.textContent = `${data.active_spaces_count || 0} de ${
      data.total_spaces_count || 0
    } salas operativas`;

    dom.kpiTotalBookings.textContent = String(data.total_bookings || 0);
    dom.kpiCountCompletada.textContent = String(counts.completada || 0);
    dom.kpiCountCancelada.textContent = String(counts.cancelada || 0);

    renderSpaceRevenueSvg(data.by_space || []);
    renderHourlyOccupancySvg(data.by_hour || []);
  }

  function renderSpaceRevenueSvg(bySpace) {
    if (!bySpace.length) {
      dom.analyticsBySpace.innerHTML =
        '<p class="muted-text">No hay datos de salas para graficar.</p>';
      return;
    }

    const width = 560;
    const rowHeight = 42;
    const topPad = 14;
    const bottomPad = 12;
    const leftLabelWidth = 158;
    const rightValueWidth = 128;
    const barAreaWidth = width - leftLabelWidth - rightValueWidth;
    const height = topPad + bottomPad + bySpace.length * rowHeight;
    const maxRevenue = Math.max(
      1,
      ...bySpace.map((item) => Number(item.revenue) || 0)
    );

    const rowsSvg = bySpace
      .map((item, idx) => {
        const y = topPad + idx * rowHeight;
        const revenue = Number(item.revenue) || 0;
        const barWidth = Math.max(
          revenue > 0 ? 6 : 0,
          (revenue / maxRevenue) * barAreaWidth
        );
        const labelText =
          item.space_name.length > 22
            ? `${item.space_name.slice(0, 21)}…`
            : item.space_name;

        return `
          <g>
            <title>${escapeHtml(item.space_name)}: ${escapeHtml(
          formatCurrency(revenue)
        )} (${escapeHtml(item.bookings_count)} reservas activas, ${escapeHtml(
          formatHours(item.total_hours)
        )})</title>
            <text
              x="${leftLabelWidth - 10}"
              y="${y + 18}"
              text-anchor="end"
              font-size="12"
              font-weight="600"
              fill="#0F172A"
            >${escapeHtml(labelText)}</text>
            <rect
              x="${leftLabelWidth}"
              y="${y + 5}"
              width="${barAreaWidth}"
              height="18"
              rx="6"
              fill="#F1F5F9"
            />
            <rect
              x="${leftLabelWidth}"
              y="${y + 5}"
              width="${barWidth.toFixed(2)}"
              height="18"
              rx="6"
              fill="${item.is_active ? "#0F766E" : "#94A3B8"}"
            />
            <text
              x="${leftLabelWidth + barAreaWidth + 10}"
              y="${y + 18}"
              text-anchor="start"
              font-size="11.5"
              font-weight="600"
              fill="#334155"
            >${escapeHtml(formatCurrency(revenue))} · ${escapeHtml(
          item.bookings_count
        )}</text>
          </g>
        `;
      })
      .join("");

    dom.analyticsBySpace.innerHTML = `
      <svg
        viewBox="0 0 ${width} ${height}"
        class="svg-chart"
        role="img"
        aria-label="Gráfico de ingresos por espacio"
      >
        ${rowsSvg}
      </svg>
    `;
  }

  function renderHourlyOccupancySvg(byHour) {
    if (!byHour.length) {
      dom.analyticsByHour.innerHTML =
        '<p class="muted-text">No hay franjas horarias disponibles.</p>';
      return;
    }

    const width = 560;
    const height = 240;
    const padLeft = 38;
    const padRight = 14;
    const padTop = 24;
    const padBottom = 34;
    const plotWidth = width - padLeft - padRight;
    const plotHeight = height - padTop - padBottom;
    const colWidth = plotWidth / byHour.length;
    const barWidth = Math.max(16, colWidth * 0.58);

    const gridLines = [0, 25, 50, 75, 100]
      .map((pct) => {
        const y = padTop + plotHeight - (pct / 100) * plotHeight;
        return `
          <g>
            <line
              x1="${padLeft}"
              y1="${y.toFixed(1)}"
              x2="${width - padRight}"
              y2="${y.toFixed(1)}"
              stroke="#E2E8F0"
              stroke-dasharray="${pct === 0 ? "0" : "3 3"}"
            />
            <text
              x="${padLeft - 6}"
              y="${(y + 4).toFixed(1)}"
              text-anchor="end"
              font-size="10"
              fill="#64748B"
            >${pct}%</text>
          </g>
        `;
      })
      .join("");

    const barsSvg = byHour
      .map((item, idx) => {
        const occ = Math.min(100, Math.max(0, Number(item.occupancy_pct) || 0));
        const barHeight = (occ / 100) * plotHeight;
        const x = padLeft + idx * colWidth + (colWidth - barWidth) / 2;
        const y = padTop + plotHeight - barHeight;
        const labelX = padLeft + idx * colWidth + colWidth / 2;
        const shortHour = String(item.hour || "").slice(0, 2);

        return `
          <g>
            <title>${escapeHtml(item.hour)}: ${escapeHtml(
          occ
        )}% de ocupación del día (${escapeHtml(
          item.today_count
        )} reservas hoy · ${escapeHtml(item.bookings_count)} históricas)</title>
            <rect
              x="${x.toFixed(1)}"
              y="${padTop}"
              width="${barWidth.toFixed(1)}"
              height="${plotHeight}"
              rx="4"
              fill="#F8FAFC"
            />
            ${
              barHeight > 0
                ? `<rect
                    x="${x.toFixed(1)}"
                    y="${y.toFixed(1)}"
                    width="${barWidth.toFixed(1)}"
                    height="${Math.max(3, barHeight).toFixed(1)}"
                    rx="4"
                    fill="#0F766E"
                  />`
                : ""
            }
            ${
              occ > 0
                ? `<text
                    x="${labelX.toFixed(1)}"
                    y="${Math.max(12, y - 5).toFixed(1)}"
                    text-anchor="middle"
                    font-size="10"
                    font-weight="700"
                    fill="#0F766E"
                  >${escapeHtml(Math.round(occ))}%</text>`
                : ""
            }
            <text
              x="${labelX.toFixed(1)}"
              y="${height - 12}"
              text-anchor="middle"
              font-size="10.5"
              fill="#475569"
            >${escapeHtml(shortHour)}h</text>
          </g>
        `;
      })
      .join("");

    dom.analyticsByHour.innerHTML = `
      <svg
        viewBox="0 0 ${width} ${height}"
        class="svg-chart"
        role="img"
        aria-label="Gráfico de ocupación por franja horaria"
      >
        ${gridLines}
        ${barsSvg}
      </svg>
    `;
  }

  /* ------------------------------------------------------------------ */
  /* Modal Nueva / Editar Reserva + 26 bloques de 30 minutos            */
  /* ------------------------------------------------------------------ */

  function clearBookingFormError() {
    dom.bookingFormError.textContent = "";
    dom.bookingFormError.hidden = true;
  }

  function showBookingFormError(message) {
    dom.bookingFormError.textContent = message;
    dom.bookingFormError.hidden = false;
  }

  function getSelectedModalSpace() {
    const selectedId = Number(dom.bookingSpace.value);
    return state.allSpaces.find((s) => Number(s.id) === selectedId) || null;
  }

  function updateBookingPricePreview() {
    const space = getSelectedModalSpace();
    const startMin = hhmmToMinutes(dom.bookingStart.value);
    const endMin = hhmmToMinutes(dom.bookingEnd.value);
    const durationMin = endMin - startMin;

    if (space) {
      dom.bookingCapacityHint.textContent = `Aforo máximo de la sala: ${space.capacity} personas`;
      dom.bookingAttendees.max = String(space.capacity);
      dom.bookingRatePreview.textContent = `${formatCurrency(
        space.hourly_rate
      )}/h`;
    } else {
      dom.bookingCapacityHint.textContent = "";
      dom.bookingRatePreview.textContent = "0,00 €/h";
    }

    if (durationMin > 0) {
      const hours = durationMin / 60;
      const estimatedPrice = space ? hours * Number(space.hourly_rate) : 0;
      dom.bookingDurationPreview.textContent = formatHours(hours);
      dom.bookingPricePreview.textContent = formatCurrency(estimatedPrice);
    } else {
      dom.bookingDurationPreview.textContent = "Horario inválido";
      dom.bookingPricePreview.textContent = "0,00 €";
    }

    highlightSelectedAvailabilitySlots();
  }

  async function refreshModalAvailability() {
    const spaceId = dom.bookingSpace.value;
    const bookingDate = dom.bookingDate.value;
    if (!spaceId || !bookingDate) {
      dom.availabilitySlots.innerHTML = "";
      dom.availabilitySummary.textContent = "Selecciona sala y fecha";
      return;
    }

    const reqId = ++state.availabilityReqSeq;
    const params = new URLSearchParams({
      space_id: spaceId,
      date: bookingDate,
    });
    if (state.editingBooking && state.editingBooking.id) {
      params.set("exclude_booking_id", String(state.editingBooking.id));
    }

    dom.availabilitySummary.textContent = "Consultando disponibilidad...";
    try {
      const data = await apiRequest(`/api/availability?${params.toString()}`);
      if (reqId !== state.availabilityReqSeq) {
        return;
      }
      state.availabilityData = data;
      renderAvailabilitySlots();
    } catch (err) {
      if (reqId !== state.availabilityReqSeq) {
        return;
      }
      dom.availabilitySlots.innerHTML = "";
      dom.availabilitySummary.textContent =
        err.message || "Error al consultar disponibilidad";
    }
  }

  function renderAvailabilitySlots() {
    const data = state.availabilityData;
    if (!data || !data.slots) {
      dom.availabilitySlots.innerHTML = "";
      return;
    }

    dom.availabilitySummary.textContent = `${data.available_slots} libres · ${data.occupied_slots} ocupados`;

    dom.availabilitySlots.innerHTML = data.slots
      .map((slot) => {
        const isFree = Boolean(slot.available);
        const stateClass = isFree ? "slot-free" : "slot-occupied";
        const tooltip = isFree
          ? `Libre: ${slot.start_time} – ${slot.end_time} (clic para seleccionar)`
          : `Ocupado por ${slot.title || "reserva"} (${slot.reference_code || ""})`;

        return `
          <button
            type="button"
            class="slot-item ${stateClass}"
            data-start="${escapeHtml(slot.start_time)}"
            data-end="${escapeHtml(slot.end_time)}"
            data-available="${isFree ? "1" : "0"}"
            title="${escapeHtml(tooltip)}"
            ${isFree ? "" : "disabled"}
          >
            ${escapeHtml(slot.start_time)}–${escapeHtml(slot.end_time)}
          </button>
        `;
      })
      .join("");

    highlightSelectedAvailabilitySlots();
  }

  function highlightSelectedAvailabilitySlots() {
    const startMin = hhmmToMinutes(dom.bookingStart.value);
    const endMin = hhmmToMinutes(dom.bookingEnd.value);
    const buttons = dom.availabilitySlots.querySelectorAll(".slot-item");

    buttons.forEach((btn) => {
      if (btn.dataset.available !== "1") {
        btn.classList.remove("slot-selected");
        return;
      }
      const slotStart = hhmmToMinutes(btn.dataset.start);
      const slotEnd = hhmmToMinutes(btn.dataset.end);
      const isSelected =
        endMin > startMin && slotStart >= startMin && slotEnd <= endMin;
      btn.classList.toggle("slot-selected", isSelected);
    });
  }

  function handleAvailabilitySlotClick(slotBtn) {
    if (slotBtn.dataset.available !== "1") {
      return;
    }
    const clickedStart = slotBtn.dataset.start;
    const clickedEnd = slotBtn.dataset.end;
    const clickedStartMin = hhmmToMinutes(clickedStart);
    const clickedEndMin = hhmmToMinutes(clickedEnd);

    const currentStartMin = hhmmToMinutes(dom.bookingStart.value);
    const currentEndMin = hhmmToMinutes(dom.bookingEnd.value);

    // Si hay exactamente un bloque de 30 min seleccionado y se hace clic en uno posterior,
    // ampliamos la franja siempre que no haya bloques ocupados en medio ni supere 8 h.
    if (
      currentEndMin - currentStartMin === SLOT_MINUTES &&
      clickedStartMin > currentStartMin &&
      clickedEndMin - currentStartMin <= MAX_DURATION_MINUTES &&
      !hasOccupiedSlotBetween(currentStartMin, clickedEndMin)
    ) {
      dom.bookingEnd.value = clickedEnd;
    } else {
      dom.bookingStart.value = clickedStart;
      dom.bookingEnd.value = clickedEnd;
    }

    clearBookingFormError();
    updateBookingPricePreview();
  }

  function hasOccupiedSlotBetween(rangeStartMin, rangeEndMin) {
    if (!state.availabilityData || !state.availabilityData.slots) {
      return false;
    }
    return state.availabilityData.slots.some((slot) => {
      if (slot.available) {
        return false;
      }
      const sMin = hhmmToMinutes(slot.start_time);
      const eMin = hhmmToMinutes(slot.end_time);
      return sMin < rangeEndMin && eMin > rangeStartMin;
    });
  }

  function openNewBookingModal(prefill = {}) {
    state.editingBooking = null;
    clearBookingFormError();
    dom.bookingForm.reset();

    dom.bookingId.value = "";
    dom.bookingModalTitle.textContent = "Nueva Reserva";
    dom.bookingModalRef.textContent = "";
    dom.bookingModalRef.hidden = true;
    dom.bookingSubmitBtn.textContent = "Confirmar Reserva";

    if (prefill.spaceId && dom.bookingSpace.querySelector(`option[value="${prefill.spaceId}"]`)) {
      dom.bookingSpace.value = String(prefill.spaceId);
    } else if (dom.bookingSpace.options.length > 0) {
      dom.bookingSpace.selectedIndex = 0;
    }

    dom.bookingDate.value = prefill.bookingDate || formatDateOffset(0);
    dom.bookingStart.value = prefill.startTime || "09:00";
    dom.bookingEnd.value = prefill.endTime || "10:00";
    dom.bookingAttendees.value = String(prefill.attendees || 2);

    dom.bookingModal.hidden = false;
    updateBookingPricePreview();
    refreshModalAvailability();
    dom.bookingTitle.focus();
  }

  function openEditBookingModal(booking) {
    if (!booking) {
      return;
    }
    if (booking.status === "cancelada") {
      showToast("No se puede editar una reserva cancelada.", "warning");
      return;
    }

    state.editingBooking = booking;
    clearBookingFormError();

    // Asegurar que la sala actual exista en el select aunque esté en mantenimiento
    if (!dom.bookingSpace.querySelector(`option[value="${booking.space_id}"]`)) {
      const opt = document.createElement("option");
      opt.value = String(booking.space_id);
      opt.textContent = `${booking.space_name || `Sala #${booking.space_id}`} (Mantenimiento)`;
      dom.bookingSpace.appendChild(opt);
    }

    dom.bookingId.value = String(booking.id);
    dom.bookingModalTitle.textContent = "Editar Reserva";
    dom.bookingModalRef.textContent = `Código ${booking.reference_code}`;
    dom.bookingModalRef.hidden = false;
    dom.bookingSubmitBtn.textContent = "Guardar Cambios";

    dom.bookingSpace.value = String(booking.space_id);
    dom.bookingDate.value = booking.booking_date;
    dom.bookingStart.value = booking.start_time;
    dom.bookingEnd.value = booking.end_time;
    dom.bookingTitle.value = booking.title || "";
    dom.bookingCustomerName.value = booking.customer_name || "";
    dom.bookingCustomerEmail.value = booking.customer_email || "";
    dom.bookingAttendees.value = String(booking.attendees || 1);
    dom.bookingNotes.value = booking.notes || "";

    dom.bookingModal.hidden = false;
    updateBookingPricePreview();
    refreshModalAvailability();
    dom.bookingTitle.focus();
  }

  function closeBookingModal() {
    dom.bookingModal.hidden = true;
    state.editingBooking = null;
    clearBookingFormError();
  }

  async function handleBookingFormSubmit(event) {
    event.preventDefault();
    clearBookingFormError();

    const payload = {
      space_id: Number(dom.bookingSpace.value),
      booking_date: dom.bookingDate.value,
      start_time: dom.bookingStart.value,
      end_time: dom.bookingEnd.value,
      title: dom.bookingTitle.value.trim(),
      customer_name: dom.bookingCustomerName.value.trim(),
      customer_email: dom.bookingCustomerEmail.value.trim(),
      attendees: Number(dom.bookingAttendees.value),
      notes: dom.bookingNotes.value.trim(),
    };

    const editingId = dom.bookingId.value.trim();
    const isEdit = Boolean(editingId);
    dom.bookingSubmitBtn.disabled = true;

    try {
      const saved = await apiRequest(
        isEdit ? `/api/bookings/${editingId}` : "/api/bookings",
        {
          method: isEdit ? "PUT" : "POST",
          body: JSON.stringify(payload),
        }
      );

      closeBookingModal();
      showToast(
        isEdit
          ? `Reserva ${saved.reference_code} actualizada correctamente.`
          : `Reserva ${saved.reference_code} confirmada (${formatCurrency(
              saved.total_price
            )}).`,
        "success"
      );
      await refreshActiveView();
    } catch (err) {
      showBookingFormError(
        err.message || "No se pudo guardar la reserva."
      );
      if (err.status === 409) {
        refreshModalAvailability();
      }
    } finally {
      dom.bookingSubmitBtn.disabled = false;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Modal Añadir Espacio                                               */
  /* ------------------------------------------------------------------ */

  function clearSpaceFormError() {
    dom.spaceFormError.textContent = "";
    dom.spaceFormError.hidden = true;
  }

  function showSpaceFormError(message) {
    dom.spaceFormError.textContent = message;
    dom.spaceFormError.hidden = false;
  }

  function openNewSpaceModal() {
    clearSpaceFormError();
    dom.spaceForm.reset();
    dom.spaceModal.hidden = false;
    dom.spaceName.focus();
  }

  function closeSpaceModal() {
    dom.spaceModal.hidden = true;
    clearSpaceFormError();
  }

  async function handleSpaceFormSubmit(event) {
    event.preventDefault();
    clearSpaceFormError();

    const payload = {
      name: dom.spaceName.value.trim(),
      category: dom.spaceCategory.value.trim(),
      floor: dom.spaceFloor.value.trim(),
      capacity: Number(dom.spaceCapacity.value),
      hourly_rate: Number(dom.spaceHourlyRate.value),
      equipment: dom.spaceEquipment.value.trim(),
    };

    dom.spaceSubmitBtn.disabled = true;
    try {
      const created = await apiRequest("/api/spaces", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      closeSpaceModal();
      showToast(`Espacio "${created.name}" añadido al catálogo.`, "success");
      await loadAllSpacesCatalog();
      await refreshActiveView();
    } catch (err) {
      showSpaceFormError(err.message || "No se pudo crear el espacio.");
    } finally {
      dom.spaceSubmitBtn.disabled = false;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Enlace de eventos e inicialización                                 */
  /* ------------------------------------------------------------------ */

  function bindEvents() {
    // Pestañas
    dom.tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        switchView(tab.dataset.view);
      });
    });

    // Botones globales
    dom.btnNewBooking.addEventListener("click", () => openNewBookingModal());
    dom.btnNewSpace.addEventListener("click", openNewSpaceModal);
    dom.btnExportCsv.addEventListener("click", exportBookingsCsv);

    // Filtros Espacios
    const debouncedLoadSpaces = debounce(() => {
      loadSpaces().catch((err) => showToast(err.message, "error"));
    }, 220);
    dom.spacesFilterQ.addEventListener("input", debouncedLoadSpaces);
    dom.spacesFilterCapacity.addEventListener("input", debouncedLoadSpaces);
    dom.spacesFilterCategory.addEventListener("change", () =>
      loadSpaces().catch((err) => showToast(err.message, "error"))
    );
    dom.spacesFilterActive.addEventListener("change", () =>
      loadSpaces().catch((err) => showToast(err.message, "error"))
    );
    dom.spacesFilterReset.addEventListener("click", () => {
      dom.spacesFilterQ.value = "";
      dom.spacesFilterCategory.value = "";
      dom.spacesFilterCapacity.value = "";
      dom.spacesFilterActive.value = "";
      loadSpaces().catch((err) => showToast(err.message, "error"));
    });

    // Acciones en tarjetas de espacios
    dom.spacesGrid.addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-action]");
      if (!btn) {
        return;
      }
      const spaceId = Number(btn.dataset.spaceId);
      if (btn.dataset.action === "toggle-space") {
        toggleSpaceStatus(spaceId, btn.dataset.nextActive === "true");
      } else if (btn.dataset.action === "book-space") {
        openNewBookingModal({ spaceId });
      }
    });

    // Agenda diaria
    dom.scheduleYesterday.addEventListener("click", () => {
      dom.scheduleDate.value = formatDateOffset(-1);
      loadSchedule().catch((err) => showToast(err.message, "error"));
    });
    dom.scheduleToday.addEventListener("click", () => {
      dom.scheduleDate.value = formatDateOffset(0);
      loadSchedule().catch((err) => showToast(err.message, "error"));
    });
    dom.scheduleTomorrow.addEventListener("click", () => {
      dom.scheduleDate.value = formatDateOffset(1);
      loadSchedule().catch((err) => showToast(err.message, "error"));
    });
    dom.scheduleDate.addEventListener("change", () => {
      loadSchedule().catch((err) => showToast(err.message, "error"));
    });

    dom.scheduleBoard.addEventListener("click", (event) => {
      const block = event.target.closest("[data-action='schedule-edit']");
      if (block) {
        const booking = findBookingInSchedule(block.dataset.bookingId);
        if (booking) {
          openEditBookingModal(booking);
        }
        return;
      }

      const slot = event.target.closest("[data-action='schedule-new']");
      if (!slot || slot.classList.contains("is-disabled")) {
        return;
      }
      const spaceId = Number(slot.dataset.spaceId);
      const startMin = hhmmToMinutes(slot.dataset.start);
      let endMin = Math.min(CLOSE_MINUTES, startMin + 60);

      // Si +60 min pisa otra reserva de la sala, ofrecer 30 min exactos
      const spaceObj = (state.scheduleData?.spaces || []).find(
        (s) => Number(s.id) === spaceId
      );
      if (spaceObj && spaceObj.bookings) {
        const overlapsHour = spaceObj.bookings.some(
          (b) =>
            hhmmToMinutes(b.start_time) < endMin &&
            hhmmToMinutes(b.end_time) > startMin
        );
        if (overlapsHour) {
          endMin = Math.min(CLOSE_MINUTES, startMin + SLOT_MINUTES);
        }
      }

      openNewBookingModal({
        spaceId,
        bookingDate: dom.scheduleDate.value,
        startTime: slot.dataset.start,
        endTime: minutesToHhmm(endMin),
      });
    });

    // Filtros Reservas
    const debouncedLoadBookings = debounce(() => {
      loadBookings().catch((err) => showToast(err.message, "error"));
    }, 220);
    dom.bookingsFilterQ.addEventListener("input", debouncedLoadBookings);
    dom.bookingsFilterSpace.addEventListener("change", () =>
      loadBookings().catch((err) => showToast(err.message, "error"))
    );
    dom.bookingsFilterStatus.addEventListener("change", () =>
      loadBookings().catch((err) => showToast(err.message, "error"))
    );
    dom.bookingsFilterDate.addEventListener("change", () =>
      loadBookings().catch((err) => showToast(err.message, "error"))
    );
    dom.bookingsFilterReset.addEventListener("click", () => {
      dom.bookingsFilterQ.value = "";
      dom.bookingsFilterSpace.value = "";
      dom.bookingsFilterStatus.value = "";
      dom.bookingsFilterDate.value = "";
      loadBookings().catch((err) => showToast(err.message, "error"));
    });

    // Acciones en tabla de reservas
    dom.bookingsTbody.addEventListener("click", (event) => {
      const btn = event.target.closest("button[data-action]");
      if (!btn) {
        return;
      }
      const bookingId = Number(btn.dataset.bookingId);
      const action = btn.dataset.action;

      if (action === "edit-booking") {
        const booking = state.bookings.find(
          (b) => Number(b.id) === bookingId
        );
        openEditBookingModal(booking);
      } else if (action === "complete-booking") {
        changeBookingStatus(bookingId, "completada");
      } else if (action === "cancel-booking") {
        changeBookingStatus(bookingId, "cancelada");
      } else if (action === "reactivate-booking") {
        changeBookingStatus(bookingId, "confirmada");
      }
    });

    // Analítica
    dom.analyticsDate.addEventListener("change", () => {
      loadAnalytics().catch((err) => showToast(err.message, "error"));
    });
    dom.analyticsToday.addEventListener("click", () => {
      dom.analyticsDate.value = formatDateOffset(0);
      loadAnalytics().catch((err) => showToast(err.message, "error"));
    });

    // Modal Reserva
    dom.bookingModalClose.addEventListener("click", closeBookingModal);
    dom.bookingModalCancel.addEventListener("click", closeBookingModal);
    dom.bookingModal.addEventListener("click", (event) => {
      if (event.target === dom.bookingModal) {
        closeBookingModal();
      }
    });
    dom.bookingSpace.addEventListener("change", () => {
      clearBookingFormError();
      updateBookingPricePreview();
      refreshModalAvailability();
    });
    dom.bookingDate.addEventListener("change", () => {
      clearBookingFormError();
      refreshModalAvailability();
    });
    dom.bookingStart.addEventListener("change", () => {
      clearBookingFormError();
      updateBookingPricePreview();
    });
    dom.bookingEnd.addEventListener("change", () => {
      clearBookingFormError();
      updateBookingPricePreview();
    });
    dom.availabilitySlots.addEventListener("click", (event) => {
      const slotBtn = event.target.closest(".slot-item");
      if (slotBtn) {
        handleAvailabilitySlotClick(slotBtn);
      }
    });
    dom.bookingForm.addEventListener("submit", handleBookingFormSubmit);

    // Modal Espacio
    dom.spaceModalClose.addEventListener("click", closeSpaceModal);
    dom.spaceModalCancel.addEventListener("click", closeSpaceModal);
    dom.spaceModal.addEventListener("click", (event) => {
      if (event.target === dom.spaceModal) {
        closeSpaceModal();
      }
    });
    dom.spaceForm.addEventListener("submit", handleSpaceFormSubmit);

    // Tecla Escape para cerrar modales
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") {
        return;
      }
      if (!dom.bookingModal.hidden) {
        closeBookingModal();
      } else if (!dom.spaceModal.hidden) {
        closeSpaceModal();
      }
    });
  }

  async function init() {
    const todayStr = formatDateOffset(0);
    dom.scheduleDate.value = todayStr;
    dom.analyticsDate.value = todayStr;
    bindEvents();

    try {
      await loadAllSpacesCatalog();
      await loadSpaces();
    } catch (err) {
      showToast(
        err.message || "Error al inicializar los datos de AuraSpace.",
        "error"
      );
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
