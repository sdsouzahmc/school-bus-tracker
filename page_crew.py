"""Crew app (bus tablet): today's list, start with crew confirmation, explicit Check In / Check Out, handover, no-show,
offline queue + sync, encrypted roster, contingency roster, close with reconciliation and named sweep. Drivers: read-only."""
import uuid

import pandas as pd
import streamlit as st

import db
import device_store as dstore
import engine as E
import reports as R
from db import SCHOOL_STOP, TRIPS
from i18n import t
from qr_utils import decode_qr
from qr_scanner import qr_scanner
from ui import gps_fix, lines_table, msg, status_text

user = st.session_state.user
role = user["role"]
is_driver = role == "driver"
crew_role = role in ("supervisor", "caretaker", "driver")

# ------------------------------------------------------------------ which bus / device
if crew_role:
    me = db.q1("SELECT * FROM staff WHERE id=?", (user["staff_id"],))
    bus_id = me["bus_id"]
else:
    bl = db.buses()
    bus_id = st.selectbox(t("Bus"), [b["id"] for b in bl], format_func=lambda i: next(b["bus_no"] for b in bl if b["id"] == i), key="crew_bus")
bus = db.bus(bus_id)
dev = db.q1("SELECT * FROM devices WHERE bus_id=? ORDER BY status='ACTIVE' DESC, id LIMIT 1", (bus_id,))
dev_id = dev["id"] if dev else None
today = db.today()

st.title(f"📷 {bus['bus_no']} — {t('Crew app')}")
st.caption(f"{bus['route_name']} · {t('Driver')}: {db.staff_name(bus['driver_id'])} · {t('Supervisor')}: {db.staff_name(bus['supervisor_id'])} · "
           f"{t('Care-taker')}: {db.staff_name(bus['caretaker_id'])} · Device: {dev['name'] if dev else '—'}")

if dev and dev["status"] != "ACTIVE":
    msg("error", f"This device was revoked by the transport office ({dev['reason'] or 'no reason given'}). Scanning is disabled.")
    st.stop()
if is_driver:
    st.info(t("Drivers do not scan. This screen is read-only for the driver."))

K = f"b{bus_id}"
queue = dstore.load_queue(dev_id) if dev_id else []

with st.expander("📶 Device: connection & GPS", expanded=bool(queue)):
    c1, c2 = st.columns(2)
    offline = c1.toggle(t("Offline mode"), key=f"{K}_off")
    gps_off = c2.toggle(t("GPS unavailable"), key=f"{K}_gps")
    if queue:
        st.warning(f"{len(queue)} action(s) stored on this device (encrypted), waiting to sync.")
        if not offline and st.button(f"🔄 {t('Sync now')} ({len(queue)})", type="primary", disabled=is_driver):
            res = E.sync_queue(queue, user["username"], role)
            dstore.save_queue(dev_id, [])
            ok = sum(1 for _, r in res if r["ok"])
            conflicts = [r["message"] for _, r in res if r.get("conflict")]
            st.session_state[f"{K}_last"] = ("warn" if conflicts else "ok", f"Synced {ok}/{len(res)} action(s)."
                                             + (" Conflicts: " + " · ".join(conflicts) if conflicts else ""))
            st.rerun()
        if offline:
            st.caption("Turn offline mode off to sync.")


def replica(run_id, items, extra=None):
    """The device's local view: server state + queued offline actions (+ one new action), never committed."""
    con = db.connect()
    try:
        for it in items:
            if it["type"] == "event":
                E.process(it["run_id"], it["kind"], dict(it["ctx"]), badge_code=it.get("badge_code"), student_id=it.get("student_id"), con=con)
        res = None
        if extra:
            kind, ctx, badge, sid = extra
            res = E.process(run_id, kind, dict(ctx), badge_code=badge, student_id=sid, con=con)
        return res, E.run_lines(run_id, con)
    finally:
        con.rollback()
        con.close()


# ------------------------------------------------------------------ no open trip: today's list + start
run = E.open_run(bus_id)
closed_local = run and any(it["type"] == "close" and it["run_id"] == run["id"] for it in queue)

if f"{K}_last" in st.session_state and not run:
    msg(*st.session_state.pop(f"{K}_last"))

if not run:
    st.subheader(f"📋 Today's list — {today}")
    st.caption("The list of children expected on each trip is sent to the bus every day. Declared absences and approved stop/bus changes are "
               "already applied. Scan against this list: a child who is not on it is flagged as wrong bus.")
    runs_today = {r["trip_no"]: r for r in db.q("SELECT * FROM trip_runs WHERE bus_id=? AND date=?", (bus_id, today))}
    default_trip = E.trip_for_time()
    tabs = st.tabs([f"Trip {n}" + (" ✔" if n in runs_today else "") for n in TRIPS])
    for n, tab in zip(TRIPS, tabs):
        with tab:
            st.markdown(f"**{TRIPS[n]['label']}** · {TRIPS[n]['window'][0]}–{TRIPS[n]['window'][1]}")
            if n in runs_today:
                st.caption(f"Already run today ({runs_today[n]['status']}).")
                lines_table(E.run_lines(runs_today[n]["id"]))
                continue
            plan = E.manifest_for(bus_id, today, n)
            for ln in plan:
                ln["stop_name"] = db.stop(ln["stop_id"])["name"] if ln["stop_id"] is not None else ""
            mv = pd.DataFrame(plan)
            if not mv.empty:
                cnt = mv.groupby(["batch", "grp", "purpose"]).agg(Planned=("student_id", "count"),
                                                                  Absent=("status", lambda s: (s == "ABSENT_DECLARED").sum())).reset_index()
                st.dataframe(cnt.rename(columns={"batch": "Batch", "grp": "Group", "purpose": "Purpose"}), hide_index=True)
            lines_table(plan, ("name", "code", "class", "batch", "grp", "purpose", "stop_name", "status"))
            if plan:
                st.download_button(f"🖨 {t('Printable contingency roster')}", R.roster_pdf(plan, f"{bus['bus_no']} · {today} · Trip {n} roster"),
                                   file_name=f"{bus['bus_no']}_{today}_trip{n}_roster.pdf", mime="application/pdf", key=f"rost{n}")
    if dev_id:
        payload = {"bus": bus["bus_no"], "date": today, "trips": {n: E.manifest_for(bus_id, today, n) for n in TRIPS}}
        st.download_button(f"🔒 {t('Download encrypted roster')}", dstore.encrypted_roster(dev_id, payload),
                           file_name=f"{bus['bus_no']}_{today}_roster.enc", help="Encrypted with this device's key — unreadable if the tablet is lost.")

    if is_driver:
        st.stop()
    st.divider()
    st.subheader("▶ " + t("Start trip"))
    avail = [n for n in TRIPS if n not in runs_today] or [default_trip]
    st.markdown("**" + t("Which trip are you starting?") + "**")
    trip_no = st.pills(t("Trip"), avail, default=default_trip if default_trip in avail else avail[0], key=f"{K}_trip_p",
                       format_func=lambda n: f"Trip {n} · {TRIPS[n]['window'][0]}–{TRIPS[n]['window'][1]}", label_visibility="collapsed") \
        or (default_trip if default_trip in avail else avail[0])
    st.markdown(f"<span class='pill'>{TRIPS[trip_no]['label']}</span>", unsafe_allow_html=True)
    if not E.in_window(trip_no, db.now()):
        st.caption(f"ℹ Outside the scheduled window ({TRIPS[trip_no]['window'][0]}–{TRIPS[trip_no]['window'][1]}). It will show on the punctuality report.")

    def crew_pick(label, r, default):
        opts = db.q("SELECT id, name FROM staff WHERE role=? ORDER BY bus_id=? DESC, name", (r, bus_id))
        ids = [o["id"] for o in opts]
        return st.selectbox(label, ids, index=ids.index(default) if default in ids else 0,
                            format_func=lambda i: next(o["name"] for o in opts if o["id"] == i), key=f"{K}_{r}")

    with st.expander(f"👥 {t('Crew')}: {db.staff_name(bus['driver_id'])} · {db.staff_name(bus['supervisor_id'])} · "
                     f"{db.staff_name(bus['caretaker_id'])} — {t('tap to change')}"):
        d_id = crew_pick(t("Driver"), "driver", bus["driver_id"])
        s_id = crew_pick(t("Supervisor"), "supervisor", bus["supervisor_id"])
        c_id = crew_pick(t("Care-taker"), "caretaker", bus["caretaker_id"])
    conf = st.checkbox(t("Confirm crew on board"), key=f"{K}_conf")
    if st.button("▶ " + t("Start trip"), type="primary", disabled=not conf or offline, width="stretch"):
        first = SCHOOL_STOP if any(m[2] == "DROPOFF" for m in TRIPS[trip_no]["movements"]) else (db.stops_of_bus(bus_id) or [{"id": SCHOOL_STOP}])[0]["id"]
        g = gps_fix(first, gps_off)
        rid, m = E.start_run(bus_id, today, trip_no, d_id, s_id, c_id, g["lat"], g["lon"], user["username"], role, dev_id)
        st.session_state[f"{K}_last"] = ("ok" if rid else "error", m + ("" if g["gps_ok"] else " (start location missing — GPS unavailable)"))
        st.rerun()
    if offline:
        st.caption("Trips are started online (the device downloads the day's manifest). Scanning then continues offline.")
    st.stop()

# ------------------------------------------------------------------ trip in progress
lines = replica(run["id"], queue)[1] if queue else E.run_lines(run["id"])
cnt = pd.Series([ln["status"] for ln in lines]).value_counts().to_dict() if lines else {}
_th1, _th2 = st.columns([5, 1], vertical_alignment="center")
_th1.markdown(f"### Trip {run['trip_no']} · {TRIPS[run['trip_no']]['label']}")
if _th2.button("🔄 " + t("Refresh"), key=f"{K}_refresh_top", width="stretch",
               help="Reload counts, lists and the close-trip check (shows scans made on other phones too)"):
    st.rerun()
st.caption(f"Started {run['start_ts'][11:16]} by {run['started_by']} · crew: {db.staff_name(run['driver_id'])} / {db.staff_name(run['supervisor_id'])} / "
           f"{db.staff_name(run['caretaker_id'])}" + (" · 📴 OFFLINE" if offline else ""))
_cn = [(t("On board"), cnt.get("ONBOARD", 0) + cnt.get("TRANSFER_PENDING", 0), "#2E9E5B"), (t("Expected"), cnt.get("EXPECTED", 0), "#E07A1F"),
       (t("Completed"), cnt.get("COMPLETED", 0) + cnt.get("RETURNED", 0), "#3D4FD6"),
       (t("Absent"), cnt.get("ABSENT_DECLARED", 0) + cnt.get("NO_SHOW", 0), "#6B7390")]
st.markdown("<div class='crewcnt'>" + "".join(f"<div><b style='color:{c}'>{v}</b><span>{l}</span></div>" for l, v, c in _cn) + "</div>",
            unsafe_allow_html=True)

if not is_driver and not closed_local and not db.q1("SELECT id FROM events WHERE run_id=? AND result<>'REJECTED' "
                                                     "AND kind IN ('CHECK_IN','CHECK_OUT') LIMIT 1", (run["id"],)):
    with st.expander("↩ Wrong trip? Cancel it (possible until the first child is checked in)", expanded=True):
        st.caption("This trip carries: " + ", ".join(f"Batch {b} {g} {p.lower().replace('dropoff', 'drop-off')}"
                                                     for b, g, p in TRIPS[run["trip_no"]]["movements"]))
        if st.button("Cancel this trip", key=f"{K}_cancel"):
            ok, m = E.cancel_run(run["id"], user["username"], role)
            st.session_state[f"{K}_last"] = ("ok" if ok else "error", m)
            st.rerun()

if closed_local:
    msg("warn", "Trip closed on this device — <b>Pending Sync</b>. The server confirms closure only after the queued scans are synced and "
        "validated. Turn offline mode off and press Sync.")
    st.stop()

if f"{K}_last" in st.session_state:
    msg(*st.session_state[f"{K}_last"])


def stop_work(lines, stops):
    """Per stop: children to board (on) and to get off / hand over (off) still outstanding."""
    w = {}
    for s_ in stops:
        sid_ = s_["id"]
        if sid_ == SCHOOL_STOP:
            on = sum(1 for ln in lines if ln["purpose"] == "DROPOFF" and ln["status"] == "EXPECTED")
            off = sum(1 for ln in lines if ln["purpose"] == "PICKUP" and ln["status"] == "ONBOARD")
        else:
            on = sum(1 for ln in lines if ln["purpose"] == "PICKUP" and ln["status"] == "EXPECTED" and ln["stop_id"] == sid_)
            off = sum(1 for ln in lines if ln["purpose"] == "DROPOFF" and ln["status"] == "ONBOARD" and ln["stop_id"] == sid_)
        w[sid_] = {"on": on, "off": off, "any": bool(on or off)}
    return w


def next_stop(lines, stops, work):
    """Suggested next stop: board drop-off children at school first, then route stops in order, then school hand-over."""
    if work[SCHOOL_STOP]["on"]:
        return SCHOOL_STOP
    for s_ in stops:
        if s_["id"] != SCHOOL_STOP and work[s_["id"]]["any"]:
            return s_["id"]
    if work[SCHOOL_STOP]["off"]:
        return SCHOOL_STOP
    return None


def suggest_action(stop_id, work):
    w = work.get(stop_id, {"on": 0, "off": 0})
    return t("Check Out") if w["off"] and not (stop_id == SCHOOL_STOP and w["on"]) else t("Check In")


def _work_text(w):
    parts = []
    if w["off"]:
        parts.append(f"⬇ {w['off']} {t('to get off')}")
    if w["on"]:
        parts.append(f"⬆ {w['on']} {t('to board')}")
    return " · ".join(parts) or t("nothing to do here")


def submit(kind, badge=None, sid=None, method="QR", extra=None, ctx=None):
    """Send one crew action to the server (or to the device queue when offline)."""
    if ctx is None:
        ctx = {"operator": user["display_name"], "role": role, "device_id": dev_id, "stop_id": st.session_state.get(f"{K}_stop", SCHOOL_STOP),
               "method": method, "captured_ts": db.ts(), "client_uuid": str(uuid.uuid4())}
        ctx.update(gps_fix(ctx["stop_id"], gps_off))
        if offline:
            ctx["offline"] = True
            ctx["sync_state"] = "PENDING"
    ctx.update(extra or {})
    if offline:
        res, _ = replica(run["id"], queue, (kind, ctx, badge, sid))
        if res["ok"] and not res.get("needs"):
            queue.append({"type": "event", "run_id": run["id"], "kind": kind, "ctx": ctx, "badge_code": badge, "student_id": sid})
            dstore.save_queue(dev_id, queue)
            res["message"] += " · 📴 saved on device, will sync"
    else:
        res = E.process(run["id"], kind, ctx, badge_code=badge, student_id=sid)
    st.session_state.pop(f"{K}_pending", None)
    if res.get("needs"):
        st.session_state[f"{K}_pending"] = {"kind": kind, "badge": badge, "sid": sid, "ctx": ctx, "needs": res["needs"], "allowed": res.get("allowed")}
    elif "Over-capacity needs" in res["message"]:
        st.session_state[f"{K}_pending"] = {"kind": kind, "badge": badge, "sid": sid, "ctx": ctx, "needs": "capacity"}
    st.session_state[f"{K}_last"] = (res["level"], res["message"])


if not is_driver:
    stops = [{"id": SCHOOL_STOP, "name": t("School")}] + db.stops_of_bus(bus_id)
    work = stop_work(lines, stops)
    nxt = next_stop(lines, stops, work)
    if f"{K}_stop" not in st.session_state:
        st.session_state[f"{K}_stop"] = nxt or SCHOOL_STOP
    if f"{K}_act" not in st.session_state:
        st.session_state[f"{K}_act"] = suggest_action(st.session_state[f"{K}_stop"], work)
    st.session_state[f"{K}_stopp"] = st.session_state[f"{K}_stop"]
    _c = st.session_state[f"{K}_stop"]
    _sig = (_c, work[_c]["off"], work[_c]["on"])
    if st.session_state.get(f"{K}_worksig") not in (None, _sig) and st.session_state.get(f"{K}_worksig")[0] == _c:
        # counts at this stop changed (a scan landed): flip the action when one direction is finished
        if work[_c]["off"] == 0 and work[_c]["on"]:
            st.session_state[f"{K}_act"] = t("Check In")
        elif work[_c]["on"] == 0 and work[_c]["off"]:
            st.session_state[f"{K}_act"] = t("Check Out")
    st.session_state[f"{K}_worksig"] = _sig

    def _go(stop_id):
        st.session_state[f"{K}_stop"] = stop_id
        st.session_state[f"{K}_act"] = suggest_action(stop_id, work)

    def _pick_stop():
        v = st.session_state.get(f"{K}_stopp")
        if v is not None:
            _go(v)

    cur = st.session_state[f"{K}_stop"]
    name_of = {s["id"]: s["name"] for s in stops}
    with st.container(border=True):
        if nxt is None:
            st.markdown(f"✅ **{t('All stops done')}** — {t('sweep the bus and close the trip below.')}")
        elif nxt != cur:
            w = work[nxt]
            pc1, pc2 = st.columns([3, 2], vertical_alignment="center")
            pc1.markdown(f"👉 **{t('Next stop')}: {name_of[nxt]}** — " + _work_text(w))
            pc2.button(f"➡ {t('Go to')} {name_of[nxt]}", type="primary", width="stretch", on_click=_go, args=(nxt,), key=f"{K}_gonext")
        else:
            st.markdown(f"📍 **{t('You are at')} {name_of[cur]}** — " + (_work_text(work[cur]) if work[cur]["any"] else t("nothing to do here")))
        st.pills(t("Current stop"), [s["id"] for s in stops], key=f"{K}_stopp", on_change=_pick_stop,
                 format_func=lambda i: f"{'✓ ' if not work[i]['any'] else ''}{name_of[i]}" + (f"  ↓{work[i]['off']}" if work[i]["off"] else "")
                 + (f"  ↑{work[i]['on']}" if work[i]["on"] else ""))
        action = st.segmented_control(t("Action"), [t("Check In"), t("Check Out")], key=f"{K}_act", width="stretch",
                                      format_func=lambda a: ("⬆ " if a == t("Check In") else "⬇ ") + a) or t("Check In")
    kind = "CHECK_IN" if action == t("Check In") else "CHECK_OUT"

    pend = st.session_state.get(f"{K}_pending")
    if pend:
        with st.container(border=True):
            if pend["needs"] == "recipient":
                st.markdown("**" + t("Handed to (authorized recipient)") + "**")
                opts = [a["name"] for a in pend["allowed"] or []] + ["__NONE__"]
                lab = {a["name"]: f"{a['name']} — {a['relation']} · {a['phone']}" for a in pend["allowed"] or []}
                lab["__NONE__"] = "⛔ " + t("No approved recipient present")
                pick = st.radio("Recipient", opts, format_func=lab.get, label_visibility="collapsed", key=f"{K}_rec")
                if st.button(t("Confirm handover"), type="primary"):
                    submit(pend["kind"], pend["badge"], pend["sid"], ctx=pend["ctx"], extra={"recipient": pick})
                    st.rerun()
            elif pend["needs"] == "receiver":
                st.markdown("**" + t("Received by (school staff)") + "**")
                rec = [r["name"] for r in db.q("SELECT name FROM staff WHERE role='receiving' ORDER BY name")]
                pick = st.pills("Receiver", rec, default=rec[0] if rec else None, label_visibility="collapsed", key=f"{K}_rcv") or (rec[0] if rec else None)
                if st.button(t("Confirm handover"), type="primary"):
                    submit(pend["kind"], pend["badge"], pend["sid"], ctx=pend["ctx"], extra={"received_by": pick})
                    st.rerun()
            elif pend["needs"] == "capacity":
                st.markdown("**Bus is full — supervisor override**")
                why = st.text_input(t("Reason"), key=f"{K}_capwhy")
                if st.button("Override and check in", disabled=not why.strip()):
                    submit(pend["kind"], pend["badge"], pend["sid"], ctx=pend["ctx"], extra={"capacity_override": why.strip()})
                    st.rerun()
            if st.button("Cancel"):
                st.session_state.pop(f"{K}_pending")
                st.rerun()

    tab_cam, tab_type, tab_man, tab_photo = st.tabs(["📷 " + t("Scan badge with camera"), "⌨️ " + t("Badge reader / type code"),
                                                     "✍️ " + t("Manual entry"), "📸 Photo scan"])
    with tab_cam:
        st.caption("Uses the BACK camera and scans continuously — hold the badge inside the square; it is recorded automatically "
                   "(beep). Set the stop and Check In / Check Out first. Allow camera access the first time.")
        val = qr_scanner(key=f"{K}_live")
        if val and val.get("nonce") and val["nonce"] != st.session_state.get(f"{K}_nonce"):
            st.session_state[f"{K}_nonce"] = val["nonce"]
            submit(kind, badge=val["code"], method="QR")
            st.rerun()
    with tab_photo:
        st.caption("Backup: take a photo of the badge (if the live scanner does not start on this device).")
        shot = st.camera_input("QR", label_visibility="collapsed", key=f"{K}_cam{st.session_state.get(f'{K}_camn', 0)}")
        if shot is not None:
            code = decode_qr(shot.getvalue())
            st.session_state[f"{K}_camn"] = st.session_state.get(f"{K}_camn", 0) + 1
            if code:
                submit(kind, badge=code, method="QR")
            else:
                st.session_state[f"{K}_last"] = ("error", "No QR code found — hold the badge closer and try again.")
            st.rerun()
    with tab_type:
        with st.form(f"{K}_typed", clear_on_submit=True):
            code = st.text_input(t("Badge code"), placeholder="Scan with a USB/Bluetooth reader or type the code")
            if st.form_submit_button(t("Submit"), type="primary") and code.strip():
                submit(kind, badge=code.strip(), method="READER")
                st.rerun()
    with tab_man:
        st.caption("Only when the badge is missing or unreadable. Needs a reason and a second crew member who verified the child.")
        opts = {ln["student_id"]: f"{ln['name']} · {ln['class']} · {ln['stop_name'] or t('School')} · {status_text(ln['status'])}" for ln in lines}
        allst = db.q("SELECT id, name, code FROM students WHERE active=1 ORDER BY name")
        for s in allst:
            opts.setdefault(s["id"], f"{s['name']} ({s['code']}) — not on this list")
        sid = st.selectbox(t("Student"), list(opts), format_func=opts.get, index=None, placeholder="Search name…", key=f"{K}_mansid")
        _why_opts = ["Badge forgotten", "Badge damaged / unreadable", "Camera / reader fault", "Paper roster entry"]
        why = st.pills(t("Reason"), _why_opts, default=_why_opts[0], key=f"{K}_manwhy") or _why_opts[0]
        crew_names = [db.staff_name(run["supervisor_id"]), db.staff_name(run["caretaker_id"]), db.staff_name(run["driver_id"])]
        _ver_opts = [n for n in crew_names if n and n != user["display_name"]] or crew_names
        ver = st.pills(t("Verified by"), _ver_opts, default=_ver_opts[0], key=f"{K}_manver") or _ver_opts[0]
        if st.button(t("Submit"), disabled=sid is None, key=f"{K}_mango"):
            submit(kind, sid=sid, method="MANUAL", extra={"manual_reason": why, "verified_by": ver})
            st.rerun()

cur_stop = st.session_state.get(f"{K}_stop", SCHOOL_STOP)
_arrive = [ln for ln in lines if ln["status"] == "ONBOARD" and ln["purpose"] == "PICKUP"]
if not is_driver and _arrive and cur_stop == SCHOOL_STOP:
    with st.container(border=True):
        st.markdown(f"**🏫 Arrived at school — hand over {len(_arrive)} pickup child(ren) to receiving staff**")
        st.caption("Records a separate school check-out for every child, with the receiving staff member's name. "
                   "Children still on a drop-off route are not affected.")
        _rcv = [r["name"] for r in db.q("SELECT name FROM staff WHERE role='receiving' ORDER BY name")]
        _who = st.pills(t("Received by (school staff)"), _rcv, default=_rcv[0] if _rcv else None, key=f"{K}_bulkrcv") or (_rcv[0] if _rcv else None)
        if st.button(f"✅ Hand over all {len(_arrive)}", type="primary", key=f"{K}_bulkgo", width="stretch"):
            _ok = 0
            for ln in _arrive:
                _ctx = {"operator": user["display_name"], "role": role, "device_id": dev_id, "stop_id": SCHOOL_STOP, "method": "GROUP_HANDOVER",
                        "captured_ts": db.ts(), "client_uuid": str(uuid.uuid4()), "received_by": _who, **gps_fix(SCHOOL_STOP, gps_off)}
                if offline:
                    _ctx.update(offline=True, sync_state="PENDING")
                    queue.append({"type": "event", "run_id": run["id"], "kind": "CHECK_OUT", "ctx": _ctx, "badge_code": None, "student_id": ln["student_id"]})
                    _ok += 1
                else:
                    _ok += bool(E.process(run["id"], "CHECK_OUT", _ctx, student_id=ln["student_id"])["ok"])
            if offline:
                dstore.save_queue(dev_id, queue)
            st.session_state[f"{K}_last"] = ("ok", f"{_ok} child(ren) handed over at school to {_who}." + (" · 📴 saved on device, will sync" if offline else ""))
            st.rerun()

st.divider()
_auto = st.toggle("🔄 Auto-refresh lists every 10 s (shows scans made on other phones too)", value=True, key=f"{K}_auto")


@st.fragment(run_every=10 if _auto else None)
def _lists_panel():
    cur_stop = st.session_state.get(f"{K}_stop", SCHOOL_STOP)
    _q = dstore.load_queue(dev_id) if dev_id else []
    _lines = replica(run["id"], _q)[1] if _q else E.run_lines(run["id"])
    _cnt = pd.Series([ln["status"] for ln in _lines]).value_counts().to_dict() if _lines else {}
    h1, h2 = st.columns([1, 3])
    if h1.button("🔄 Refresh", key=f"{K}_refresh", help="Reload the whole screen: counts, lists and the close-trip check"):
        st.rerun()
    h2.caption(f"Updated {db.now():%H:%M:%S} · on board {_cnt.get('ONBOARD', 0) + _cnt.get('TRANSFER_PENDING', 0)} · "
               f"expected {_cnt.get('EXPECTED', 0)} · completed {_cnt.get('COMPLETED', 0) + _cnt.get('RETURNED', 0)}")
    _up = []
    for _s in [{"id": SCHOOL_STOP, "name": t("School"), "seq": 0}] + db.stops_of_bus(bus_id):
        _pick = sum(1 for ln in _lines if ln["purpose"] == "PICKUP" and ln["status"] == "EXPECTED" and ln["stop_id"] == _s["id"])
        _board = sum(1 for ln in _lines if ln["purpose"] == "DROPOFF" and ln["status"] == "EXPECTED") if _s["id"] == SCHOOL_STOP else 0
        _drop = sum(1 for ln in _lines if ln["purpose"] == "DROPOFF" and ln["status"] == "ONBOARD" and ln["stop_id"] == _s["id"])
        _hand = sum(1 for ln in _lines if ln["purpose"] == "PICKUP" and ln["status"] == "ONBOARD") if _s["id"] == SCHOOL_STOP else 0
        if _pick or _board or _drop or _hand:
            _up.append({"Stop": _s["name"], "To board": _pick + _board, "To get off": _drop + _hand})
    with st.expander(f"🗺️ Upcoming stops ({len(_up)})", expanded=bool(_up)):
        if _up:
            _cur_name = t("School") if cur_stop == SCHOOL_STOP else next((s["name"] for s in db.stops_of_bus(bus_id) if s["id"] == cur_stop), "")
            _df = pd.DataFrame(_up)
            st.dataframe(_df.style.apply(lambda r: ["background-color:#FFF4C2;font-weight:600" if r["Stop"] == _cur_name else "" for _ in r], axis=1),
                         hide_index=True, width="stretch")
        else:
            st.caption("No stops left — every child is accounted for.")
    left, right = st.columns(2)
    with left:
        ob = [ln for ln in _lines if ln["status"] in ("ONBOARD", "TRANSFER_PENDING")]
        off_here = [ln for ln in ob if (ln["purpose"] == "DROPOFF" and ln["stop_id"] == cur_stop) or
                    (ln["purpose"] == "PICKUP" and cur_stop == SCHOOL_STOP and ln["status"] == "ONBOARD")]
        st.subheader(f"🟢 {t('On board')} ({len(ob)})")
        if off_here and not is_driver:
            st.markdown(f"<span class='pill orange'>📍 {len(off_here)} {t('get off at this stop')}</span>", unsafe_allow_html=True)
        lines_table(ob, ("name", "class", "purpose", "stop_name", "status", "entry_ts"), highlight={ln["id"] for ln in off_here})
    with right:
        ex = [ln for ln in _lines if ln["status"] == "EXPECTED"]
        here = [ln for ln in ex if (ln["purpose"] == "PICKUP" and ln["stop_id"] == cur_stop) or (ln["purpose"] == "DROPOFF" and cur_stop == SCHOOL_STOP)]
        st.subheader(f"⏳ {t('Expected')} ({len(ex)})")
        if here and not is_driver:
            st.markdown(f"<span class='pill orange'>📍 {len(here)} {t('expected at this stop')}</span>", unsafe_allow_html=True)
        lines_table(sorted(ex, key=lambda ln: (ln not in here, ln["stop_seq"] or 0)), ("name", "class", "purpose", "stop_name"),
                    highlight={ln["id"] for ln in here})
        if ex and not is_driver:
            _cand = here or ex
            st.markdown("**" + t("Mark no-show") + "**" + (f" — {t('children expected at this stop')}" if here else ""))
            ns = st.pills(t("Mark no-show"), [ln["student_id"] for ln in _cand[:15]], key=f"{K}_ns", label_visibility="collapsed",
                          format_func=lambda i: next(ln["name"] for ln in _cand if ln["student_id"] == i))
            if st.button("🚫 " + t("Mark no-show"), disabled=ns is None, width="stretch", key=f"{K}_nsgo"):
                submit("NO_SHOW", sid=ns, method="CREW")
                st.rerun()


_lists_panel()

with st.expander(t("All children on this trip")):
    lines_table(lines, ("name", "code", "class", "batch", "grp", "purpose", "stop_name", "status", "entry_ts", "exit_ts", "handover",
                        "recipient_name", "received_by"))
    st.download_button(f"🖨 {t('Printable contingency roster')}", R.roster_pdf(lines, f"{bus['bus_no']} · {run['date']} · Trip {run['trip_no']}"),
                       file_name=f"{bus['bus_no']}_trip{run['trip_no']}_roster.pdf", mime="application/pdf")
with st.expander(t("Scan log")):
    ev = db.q("""SELECT substr(e.captured_ts,12,8) AS Captured, substr(e.received_ts,12,8) AS Received, e.kind AS Action, s.name AS Student,
                 e.result AS Result, e.reason AS Detail, e.method AS Method, e.operator AS Operator, e.connectivity AS Net
                 FROM events e LEFT JOIN students s ON s.id=e.student_id WHERE e.run_id=? ORDER BY e.id DESC""", (run["id"],))
    st.dataframe(ev, hide_index=True, width="stretch")
    if queue:
        st.caption(f"+ {len(queue)} action(s) on the device not yet synced")

if is_driver:
    st.stop()

# ------------------------------------------------------------------ close
st.divider()
st.subheader("⏹ " + t("Close trip"))
bl = [ln for ln in lines if ln["status"] in E.ACTIVE_LINE]
if bl:
    msg("error", f"{t('Cannot close: every child must be accounted for.')} {len(bl)} {t('Still to be accounted for').lower()}: "
        + ", ".join(f"{ln['name']} ({status_text(ln['status'])})" for ln in bl[:12]) + (" …" if len(bl) > 12 else ""))
    st.caption("Check out, mark no-show, return to school, or ask the office to decide pending transfers.")
crew_names = {run["supervisor_id"]: db.staff_name(run["supervisor_id"]), run["caretaker_id"]: db.staff_name(run["caretaker_id"])}
_sw_opts = list(dict.fromkeys(n for n in crew_names.values() if n))
sweeper = st.pills(t("Physical sweep done by"), _sw_opts, default=_sw_opts[-1] if _sw_opts else None, key=f"{K}_sweep") or (_sw_opts[-1] if _sw_opts else None)
swept = st.checkbox(t("I walked the full bus and checked every seat"), key=f"{K}_swept")
with st.expander("Final crew (change only if crew changed during the trip)"):
    f1, f2, f3 = st.columns(3)

    def fpick(col, label, r, default):
        opts = db.q("SELECT id, name FROM staff WHERE role=? ORDER BY bus_id=? DESC, name", (r, bus_id))
        ids = [o["id"] for o in opts]
        return col.selectbox(label, ids, index=ids.index(default) if default in ids else 0,
                             format_func=lambda i: next(o["name"] for o in opts if o["id"] == i), key=f"{K}_f{r}")
    fd = fpick(f1, t("Driver"), "driver", run["driver_id"])
    fs = fpick(f2, t("Supervisor"), "supervisor", run["supervisor_id"])
    fc = fpick(f3, t("Care-taker"), "caretaker", run["caretaker_id"])
if st.button("⏹ " + t("Close trip"), type="primary", disabled=bool(bl) or not swept, width="stretch"):
    g = gps_fix(cur_stop, gps_off)
    if offline:
        queue.append({"type": "close", "run_id": run["id"], "captured_ts": db.ts(), "sweep_by": sweeper, "final": [fd, fs, fc]})
        dstore.save_queue(dev_id, queue)
        st.session_state[f"{K}_last"] = ("warn", "Closed on the device — Pending Sync.")
    else:
        ok, m, _ = E.close_run(run["id"], sweeper, fd, fs, fc, g["lat"], g["lon"], user["username"], role)
        if ok:
            m += (f" Ended {db.now():%H:%M}, GPS {g['lat']:.5f}, {g['lon']:.5f}" if g["gps_ok"] else f" Ended {db.now():%H:%M}, GPS unavailable") + \
                 f" · sweep by {sweeper} · final crew {db.staff_name(fd)} / {db.staff_name(fs)} / {db.staff_name(fc)}."
        st.session_state[f"{K}_last"] = ("ok" if ok else "error", m)
        st.session_state.pop(f"{K}_swept", None)
    st.rerun()
