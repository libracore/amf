import frappe
from frappe import _


# ==================================================
#  SECURITY CHECK
# ==================================================
def _ensure_logged_in():
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in to access this resource."), frappe.PermissionError)


# ==================================================
#  UTILITY — return active session start_time
# ==================================================
def get_last_start_time(timer_name):
    """
    Retourne le start_time de la dernière session active (où stop_time est NULL).
    """
    row = frappe.db.sql("""
        SELECT start_time
        FROM `tabWork Order Timer Table`
        WHERE parent=%s AND (stop_time IS NULL OR stop_time = '')
        ORDER BY idx DESC
        LIMIT 1
    """, (timer_name,), as_dict=True)

    return row[0].start_time if row else None


# ==================================================
#  GET TIMER DETAILS
# ==================================================
@frappe.whitelist()
def get_timer_details(work_order):
    """
    Retourne les infos propres du timer :
    - name
    - operator
    - work_order
    - status
    - total_seconds  (toujours en secondes)
    - start_time     (uniquement si une session active existe)
    """
    _ensure_logged_in()

    timer = frappe.db.get_value(
        "Timer Production",
        {"work_order": work_order},
        ["name", "operator", "status", "total_duration", "work_order"],
        as_dict=True
    )
    if not timer:
        return None

    # Toujours en secondes
    timer["total_seconds"] = int(timer.get("total_duration") or 0)

    # Dernier start_time actif
    timer["start_time"] = get_last_start_time(timer["name"])

    return timer


# ==================================================
#  GET ACTIVE TIMERS
# ==================================================
@frappe.whitelist()
def get_active_timers():
    _ensure_logged_in()

    timers = frappe.get_all(
        "Timer Production",
        filters={"status": ["in", ["IN PROCESS", "PAUSED"]]},
        fields=["work_order"]
    )

    detailed = []
    for t in timers:
        info = get_timer_details(t["work_order"])
        if info:
            detailed.append(info)

    return detailed


# ==================================================
#  SEARCH TIMER BY OF
# ==================================================
@frappe.whitelist()
def search_timer_by_of(search_input):
    _ensure_logged_in()
    if not search_input:
        frappe.throw(_("Le paramètre 'research' est manquant."))

    # check if parameter is a work_order or a trigram
    if search_input.upper().startswith("OF") or search_input.isdigit() or "-" in search_input:
        work_order = get_normalized_of_name(search_input) 
    
    else:
        # search the latest timer for the given trigram
        trigram = search_input.upper()
        timer = frappe.db.sql("""
            SELECT work_order
            FROM `tabTimer Production`
            WHERE operator=%s
            ORDER BY modified DESC
            LIMIT 1
        """, (trigram,), as_dict=True)
        if not timer:
            frappe.throw(_("Aucun timer trouvé pour l'opérateur {0}.").format(trigram))
        work_order = timer[0].work_order 

    #check if work order status is in process 
    of_status = frappe.db.get_value("Work Order", work_order, "status")
    if of_status != "In Process":
        frappe.throw(_("L'ordre de travail {0} n'est pas en statut 'En cours'. Statut actuel : {1}").format(work_order, of_status))
        

    timer = get_timer_details(work_order)

    # --- Found ---
    if timer:
        status = timer["status"].upper()

        if status in ["IN PROCESS", "PAUSED"]:
            return timer

        if status == "FINISHED":
            frappe.throw(_("Le timer associé à {0} est terminé.").format(work_order))

    # --- Create new ---
    trigram = get_trigram_from_user()
    if trigram  in ["PRD", "administrator"]:
        trigram = ""  # avoid generic trigram for production staff user
    else:
        clean_timer_trigram(trigram)
    new_timer = frappe.get_doc({
        "doctype": "Timer Production",
        "work_order": work_order,
        "operator": trigram,
        "status": "PAUSED",
        "total_duration": 0
    })
    new_timer.insert(ignore_permissions=True)

    return get_timer_details(new_timer.work_order)


# ==================================================
#  START TIMER
# ==================================================
@frappe.whitelist()
def start_timer(work_order):
    _ensure_logged_in()

    timer = frappe.get_doc("Timer Production", {"work_order": work_order})

    if timer.status == "IN PROCESS":
        return {"status": "IN PROCESS", "message": "Déjà en cours."}

    # Nouvelle session
    timer.append("sessions_list", {
        "start_time": frappe.utils.now_datetime(),
        "stop_time": None,
        "duration": 0
    })

    timer.status = "IN PROCESS"
    timer.save(ignore_permissions=True)

    return {"status": "IN PROCESS", "message": "Timer démarré."}


# ==================================================
#  PAUSE TIMER
# ==================================================
@frappe.whitelist()
def pause_timer(work_order, operator):
    _ensure_logged_in()

    timer = frappe.get_doc("Timer Production", {"work_order": work_order})

    if timer.status != "IN PROCESS":
        return {"status": "PAUSED", "message": "Timer déjà en pause."}

    # Trouver la session active
    for sess in reversed(timer.sessions_list):
        if not sess.stop_time:
            now = frappe.utils.now_datetime()
            sess.stop_time = now
            sess.operator = operator

            # already done in timer_before_save
            # delta = (now - sess.start_time).total_seconds()
            # sess.duration = delta  # STOCKAGE DANS LA TABLE

            # timer.total_duration = (timer.total_duration or 0) + delta
            break

    timer.status = "PAUSED"
    timer.save(ignore_permissions=True)

    return {"status": "PAUSED", "message": "Timer mis en pause."}



# ==================================================
#  FINISH TIMER
# ==================================================
@frappe.whitelist()
def finish_timer(work_order):
    """
    Termine un timer :
    - Si il est en PAUSED → passe en FINISHED.
    - Si il est en IN PROCESS → exécute la pause, ajoute la durée, puis FINISHED.
    - Si déjà FINISHED → renvoie un message.
    """
    _ensure_logged_in()

    timer = frappe.get_doc("Timer Production", {"work_order": work_order})
    if not timer:
        frappe.throw(_("Aucun timer trouvé pour cette OF."))

    if timer.status == "FINISHED":
        return {"status": "FINISHED", "message": "Ce timer est déjà terminé."}

    # Si en cours → faire une pause proprement avant de terminer
    if timer.status == "IN PROCESS":
        now = frappe.utils.now_datetime()

        # Trouver la session active
        for sess in reversed(timer.sessions_list):
            if not sess.stop_time:
                sess.stop_time = now
                sess.operator = timer.operator
                
                # already done in timer_before_save
                # delta = (now - sess.start_time).total_seconds()
                # sess.duration = delta
                # timer.total_duration = (timer.total_duration or 0) + delta
                break

    # Mettre FINISHED
    timer.status = "FINISHED"
    timer.operator = ""
    timer.save(ignore_permissions=True)
    
    # already in timer_before_save
    # # insérer la durée totale dans la doctype de l'OF
    # wo_doc = frappe.get_doc("Work Order", work_order)
    # wo_doc.total_duration = timer.total_duration
    
    # # obtenir la durée totale par opérateur ayant travaillé sur cette OF
    # operator_durations = {}

    # for sess in timer.sessions_list:
    #     op = sess.operator or "Inconnu"
    #     operator_durations[op] = operator_durations.get(op,0) + (sess.duration or 0)
    
    # wo_doc.duration_table = []
    # for op, dur in operator_durations.items():
    #     wo_doc.append("duration_table", {
    #         "operator": op,
    #         "duration": dur
    #     })

    # wo_doc.save(ignore_permissions=True)

    return {"status": "FINISHED", "message": "Timer terminé avec succès."}



# ==================================================
#  GET WORK ORDER ITEM
# ==================================================
@frappe.whitelist()
def get_work_order_item(work_order):
    if not work_order:
        frappe.throw(_("Work Order manquant"))

    item_data = frappe.db.get_value(
        "Work Order",
        work_order,
        ["production_item", "item_name"],
        as_dict=True
    )

    if not item_data:
        return None

    return {
        "item_code": item_data.get("production_item"),
        "item_name": item_data.get("item_name"),
    }



# ==================================================
#  UPDATE OPERATOR
# ==================================================
@frappe.whitelist()
def update_operator(work_order, operator):
    _ensure_logged_in()
    operator = operator.upper()
    # check if operator exist
    if not frappe.db.get_all("User", {"username": operator}, "name"):
        frappe.throw(_("L'opérateur {0} n'existe pas.").format(operator))

    clean_timer_trigram(operator)
    timer = frappe.get_doc("Timer Production", {"work_order": work_order})
    timer.operator = operator
    timer.save(ignore_permissions=True)

    return {"message": "Opérateur mis à jour"}



# ==================================================
# UTILITY - NORMALIZE WORK ORDER NAME
# ==================================================
def get_normalized_of_name(work_order):
    """
    Normalize a Work Order identifier to the standard format.

    Args:
        work_order (str): The work order identifier. 
            Accepted formats include:
                - Numeric only (e.g., "456")
                - Prefixed with "OF-" or "OF" (e.g., "OF-456", "OF456")
                - Lowercase or mixed case (e.g., "of_01376")
                - With suffixes (e.g., "1473-1")
            Invalid formats include non-numeric prefixes (e.g., "DN-1376").

    Returns:
        str: Normalized work order in the format "OF-XXXXX" or "OF-XXXXX-<suffix>" 
            where "XXXXX" is a zero-padded 5-digit number.

    Raises:
        frappe.ValidationError: If the input format is invalid or cannot be normalized.

    Normalization logic:
        - Converts input to uppercase.
        - Replaces underscores with hyphens.
        - Extracts the main numeric part and any suffix.
        - Pads the numeric part to 5 digits.
        - Throws an error for invalid formats.
    """
    import re
    # Normalize to uppercase, replace underscores with hyphens and trim whitespace
    work_order = work_order.upper().replace("_", "-").strip()

    # Match optional "OF" prefix (with or without hyphen), capture main number and optional suffix (-<digits>)
    match = re.match(r"^(?:OF-?)?(\d+)(?:-(\d+))?$", work_order)
    if not match:
        frappe.throw(_("Invalid Work Order format."))

    main_number = int(match.group(1))
    suffix = match.group(2)

    if suffix:
        normalized_wo = f"OF-{main_number:05d}-{suffix}"
    else:
        normalized_wo = f"OF-{main_number:05d}"

    return normalized_wo


# ==================================================
#  GET TRIGRAM FROM USER
# ==================================================
@frappe.whitelist()
def get_trigram_from_user():
    """
    Retourne le trigramme (3 premières lettres en majuscules) de l'opérateur.
    en fonction de l'utilisateur connecté.
    exemple :
      - user = "marc.chautems@amf.ch"  => "MCH"
    """
    user = frappe.session.user

    trigram = frappe.db.get_value("User", user, "username") or user
    return trigram

# ==================================================
#  CLEAN TIMER TRIGRAM
# =================================================
@frappe.whitelist()
def clean_timer_trigram(trigram):
    """
    fetch all active timers (paused, in process) with given trigram and set trigram to empty string
    """
    timers = frappe.get_all(
        "Timer Production",
        filters={"operator": trigram, "status": ["in", ["PAUSED", "IN PROCESS"]]},
        fields=["name"]
    )

    for t in timers:
        timer = frappe.get_doc("Timer Production", t["name"])
        if timer.status == "IN PROCESS":
            frappe.throw(_("L'opérateur {0} a un timer en cours pour l'OF {1}. Veuillez terminer ce timer avant de continuer.").format(trigram, timer.work_order))
        timer.operator = ""
        timer.save(ignore_permissions=True)

