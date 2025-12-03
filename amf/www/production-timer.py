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
def get_last_start_time(timer_name, operator):
    """
    Retourne le start_time de la dernière session active (où stop_time est NULL).
    """
    row = frappe.db.sql("""
        SELECT start_time
        FROM `tabWork Order Timer Table`
        WHERE parent=%s AND operator=%s AND stop_time IS NULL 
        ORDER BY idx DESC
        LIMIT 1
    """, (timer_name, operator), as_dict=True)

    return row[0].start_time if row else None


# ==================================================
#  GET TIMER DETAILS
# ==================================================
@frappe.whitelist()
def get_timer_details(work_order):
    """
    Retourne les infos propres du timer :
    - name
    - assigned_operators
    - work_order
    - status
    - total_seconds  (toujours en secondes)
    - active_sessions : liste de dicts {operator, start_time} pour chaque session active
    - dict durée totale par opérateur sur cette OF
    """
    _ensure_logged_in()

    timer = frappe.db.get_value(
        "Timer Production",
        {"work_order": work_order},
        ["name", "assigned_operators", "status", "total_duration", "work_order"],
        as_dict=True
    )
    if not timer:
        return None

    # Toujours en secondes
    timer["total_seconds"] = int(timer.get("total_duration") or 0)

    # Liste des opérateurs assignés
    operators = [
        op.strip() for op in (timer.get("assigned_operators") or "").split("/")
        if op.strip()
    ]

    active_sessions = []
    for op in operators:
        st = get_last_start_time(timer["name"], op)
        if st:
            active_sessions.append({
                "operator": op,
                "start_time": st
            })

    timer["active_sessions"] = active_sessions
    timer["operators_time"] = get_operators_time(work_order)

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
def search_timer(search_input):
    _ensure_logged_in()
    if not search_input:
        frappe.throw(_("Le paramètre 'research' est manquant."))

    # check if parameter is a work_order or a trigram
    if search_input.upper().startswith("OF") or search_input.isdigit() or "-" in search_input:
        work_order = get_normalized_of_name(search_input) 
    
    else:
        # search the latest timer with the search input as trigram in assigned_operators
        trigram = search_input.upper()
        timer = frappe.db.sql("""
            SELECT work_order
            FROM `tabTimer Production`
            WHERE assigned_operators LIKE %s
                AND status IN ("IN PROCESS", "PAUSED")
            ORDER BY modified DESC
            LIMIT 1
        """, ("%" + trigram + "%",), as_dict=True)
        if not timer:
            return None
        work_order = timer[0].work_order 

    #check if work order is submitted
    of_status = frappe.db.get_value("Work Order", work_order, "status")
    if not of_status:
        frappe.throw(_("L'OF {0} n'existe pas.").format(work_order))
    if of_status in ["Completed", "Stopped", "Cancelled"]:
        frappe.throw(_("L'OF {0} est \"{1}\".").format(work_order, of_status))

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
        clean_assignement(trigram)
    new_timer = frappe.get_doc({
        "doctype": "Timer Production",
        "work_order": work_order,
        "assigned_operators": trigram,
        "status": "PAUSED",
        "total_duration": 0
    })
    new_timer.insert(ignore_permissions=True)

    return get_timer_details(new_timer.work_order)


# ==================================================
#  START TIMER
# ==================================================
@frappe.whitelist()
def start_timer(work_order,trigram):
    _ensure_logged_in()

    timer = frappe.get_doc("Timer Production", {"work_order": work_order})

    # Nouvelle session
    timer.append("sessions_list", {
        "start_time": frappe.utils.now_datetime(),
        "stop_time": None,
        "duration": 0,
        "operator": trigram
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

    operator = operator.upper()
    timer = frappe.get_doc("Timer Production", {"work_order": work_order})

    paused = False

    now = frappe.utils.now_datetime()

    # Fermer la session ACTIVE de cet opérateur
    for sess in timer.sessions_list:
        if sess.operator == operator and sess.stop_time is None:
            sess.stop_time = now
            paused = True
            break

    if not paused:
        frappe.msgprint(_("Aucune session active trouvée pour l'opérateur {0}.").format(operator))
        return None

    # Statut global = IN PROCESS s'il reste au moins une session active
    remaining_active = any(s.stop_time is None for s in timer.sessions_list)
    timer.status = "IN PROCESS" if remaining_active else "PAUSED"

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
    - Si il est en IN PROCESS → exécute la pause, puis FINISHED.
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
                sess.comment = "Auto-pause lors du FINISH"

    # Mettre FINISHED
    timer.status = "FINISHED"
    timer.assigned_operators = ""
    timer.save(ignore_permissions=True)

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
def add_operator(work_order, operator):
    """
    Met à jour l'opérateur assigné au timer de l'OF.
    assigned_operators = "" => operator
    assigned_operators = "MCH/ARD" => "MCH/ARD/<operator>"
    assigned_operators = "MCH" => "MCH/<operator>" 
    Nettoie les anciennes assignations avant de mettre à jour.
    """
    _ensure_logged_in()
    
    operator = operator.upper()

    
    # check if operator exist
    if not frappe.db.get_all("User", {"username": operator}, "name"):
        frappe.throw(_("L'opérateur {0} n'existe pas.").format(operator))

    clean_assignement(operator)
    
    timer = frappe.get_doc("Timer Production", {"work_order": work_order})
    
    exisiting_ops = []
    if timer.assigned_operators:
        exisiting_ops = [op.strip() for op in timer.assigned_operators.split("/") if op.strip()]

    if operator not in exisiting_ops:
        exisiting_ops.append(operator)

    timer.assigned_operators = "/".join(exisiting_ops)


    timer.save(ignore_permissions=True)

    return {"message": "Opérateur mis à jour"}

@frappe.whitelist()
def change_operator(work_order, old_operator, new_operator):
    """
    Remplace un opérateur assigné au timer de l'OF par un autre.
    assigned_operators = "MCH/ARD" , old_operator = "ARD", new_operator = "CBE" => "MCH/CBE"
    assigned_operators = "MCH" , old_operator = "MCH", new_operator = "CBE" => "CBE"
    """
    _ensure_logged_in()
    
    old_operator = old_operator.upper()
    new_operator = new_operator.upper()
    
    # check if new_operator exist
    if not frappe.db.get_all("User", {"username": new_operator}, "name"):
        frappe.throw(_("L'opérateur {0} n'existe pas.").format(new_operator))

    clean_assignement(new_operator)

    timer = frappe.get_doc("Timer Production", {"work_order": work_order})
    
    # check is session is active for old_operator
    if timer.status == "IN PROCESS":
        for sess in reversed(timer.sessions_list):
            if sess.operator == old_operator and sess.stop_time is None:
                # make a pause on this session
                now = frappe.utils.now_datetime()
                sess.stop_time = now
                sess.comment = "Auto-pause avant changement d'opérateur"
                break
            
    split_ops = [op.strip() for op in timer.assigned_operators.split("/") if op.strip()]
    if old_operator in split_ops:
        split_ops.remove(old_operator)
    if new_operator not in split_ops:
        split_ops.append(new_operator)
    timer.assigned_operators = "/".join(split_ops)

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
def clean_assignement(trigram):
    """
    fetch all active timers (paused, in process) with its assigned_operators and remove trigram to avoid multiple assignments
    if assigned_operators = "MCH/ARD/CBE" and trigram = "ARD" => assigned_operators = "MCH/CBE"
    if assigned_operators = "MCH/ARD" and trigram = "ARD" => assigned_operators = "MCH"
    if assigned_operators = "ARD" and trigram = "ARD" => assigned_operators = ""
    also, if timer is in process, make a pause before removing the trigram
    """

    trigram = trigram.upper()
    timers = frappe.get_all(
        "Timer Production",
        filters={
            "assigned_operators": ["like", f"%{trigram}%"],
            "status": ["in", ["PAUSED", "IN PROCESS"]]},
        fields=["name", "work_order"]
    )

    for t in timers:
        # check if work_order status is not Completed, Stopped or Cancelled
        of_status = frappe.db.get_value("Work Order", t["work_order"], "status")
        if of_status in ["Completed", "Stopped", "Cancelled"]:
            finish_timer(t["work_order"])
            continue



        timer = frappe.get_doc("Timer Production", t["name"])
        
        if timer.status == "IN PROCESS":
            # make a pause and check status
            now = frappe.utils.now_datetime()
            
            for sess in reversed(timer.sessions_list):
                
                if sess.operator == trigram and sess.stop_time is None:
                    # frappe.msgprint("Vous travaillez actuellement sur le timer: {}, mise en pause de la session liée à votre trigramme".format(timer.name))
                    sess.stop_time = now
                    sess.comment = "Auto-pause avant nettoyage assignation"
                    #sess.operator = trigram
                    break
                
            remaining_active = any(sess.stop_time is None for sess in timer.sessions_list)
            if remaining_active:
                timer.status = "IN PROCESS"
            else:
                timer.status = "PAUSED"

        split_ops = [op.strip() for op in timer.assigned_operators.split("/") if op.strip()]
        if trigram in split_ops:
            split_ops.remove(trigram)
        timer.assigned_operators = "/".join(split_ops)
        timer.save(ignore_permissions=True)



# ==================================================
#  GET OPERATORS TIME ON A WORK ORDER
# ==================================================
@frappe.whitelist()
def get_operators_time(work_order):
    """
    Retourne le temps total passé par chaque opérateur sur l'OF.
    Résultat : dict {operator: total_seconds}
    """
    _ensure_logged_in()

    sessions = frappe.db.sql("""
        SELECT operator, SUM(TIMESTAMPDIFF(SECOND, start_time, stop_time)) AS total_seconds
        FROM `tabWork Order Timer Table`
        WHERE parenttype='Timer Production' AND parent IN (
            SELECT name FROM `tabTimer Production` WHERE work_order=%s
        )
        GROUP BY operator
    """, (work_order,), as_dict=True)

    result = {}
    for sess in sessions:
        result[sess.operator] = int(sess.total_seconds or 0)

    return result