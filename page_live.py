"""Office: live trips, map, alerts and drill-down to any trip's manifest and events."""
from datetime import date

import pandas as pd
import streamlit as st

import db
import engine as E
import reports as R
from db import TRIPS
from ui import bus_cards, bus_map, bus_positions, lines_table

st.title("Live Trips")
runs_all = db.q("SELECT DISTINCT date FROM trip_runs ORDER BY date DESC")
dates = [r["date"] for r in runs_all]
c1, c2 = st.columns([1, 3])
d = c1.date_input("Date", value=date.fromisoformat(db.today() if db.today() in dates or not dates else dates[0]))
auto = c2.toggle("Auto-refresh every 15 s", value=False)
D = d.isoformat()


@st.fragment(run_every=15 if auto else None)
def board():
    fresh, pend = R.freshness()
    st.caption(f"Data as of {fresh} · trips pending sync: {pend} · now {db.ts()}")
    k = db.q1("""SELECT SUM(r.status IN ('IN_PROGRESS','PENDING_SYNC')) live, SUM(r.status='CLOSED') closed,
                 (SELECT COUNT(*) FROM manifest m JOIN trip_runs r2 ON r2.id=m.run_id WHERE r2.date=? AND m.status IN ('ONBOARD','TRANSFER_PENDING')) onb,
                 (SELECT COUNT(*) FROM manifest m JOIN trip_runs r2 ON r2.id=m.run_id WHERE r2.date=? AND r2.status<>'PLANNED'
                    AND m.status IN ('EXPECTED','ONBOARD','TRANSFER_PENDING')) unacc
                 FROM trip_runs r WHERE r.date=?""", (D, D, D))
    inc = db.q1("SELECT COUNT(*) n, SUM(severity IN ('HIGH','CRITICAL')) hi FROM incidents WHERE status<>'RESOLVED'")
    m = st.columns(5)
    m[0].metric("Trips in progress", k["live"] or 0)
    m[1].metric("Trips closed", k["closed"] or 0)
    m[2].metric("Children on board", k["onb"] or 0)
    m[3].metric("Not yet accounted for", k["unacc"] or 0)
    m[4].metric("Open incidents", inc["n"] or 0, delta=f"{inc['hi'] or 0} high/critical", delta_color="inverse" if inc["hi"] else "off")
    hi = db.q("""SELECT i.ts, i.kind, i.details, b.bus_no FROM incidents i LEFT JOIN buses b ON b.id=i.bus_id
                 WHERE i.status<>'RESOLVED' AND i.severity IN ('HIGH','CRITICAL') ORDER BY i.id DESC LIMIT 5""")
    for h in hi:
        st.markdown(f"<div class='error'>🚨 <b>{h['kind'].replace('_', ' ')}</b> · {h['bus_no'] or ''} · {h['ts'][:16]} — {h['details']}</div>",
                    unsafe_allow_html=True)
    open_runs = db.q("SELECT * FROM trip_runs WHERE date=? AND status IN ('IN_PROGRESS','PENDING_SYNC') ORDER BY bus_id", (D,))
    if open_runs:
        nonb = db.q1(f"SELECT COUNT(*) n FROM manifest WHERE status IN ('ONBOARD','TRANSFER_PENDING') AND run_id IN ({','.join('?' * len(open_runs))})",
                     [r["id"] for r in open_runs])["n"]
        noff = sum(r["status"] == "PENDING_SYNC" for r in open_runs)
        st.markdown(f"<span class='pill' style='padding:6px 12px'>{len(open_runs) - noff} moving</span> "
                    f"<span class='pill orange' style='padding:6px 12px'>{noff} offline</span> "
                    f"<span class='pill grey' style='padding:6px 12px;background:#fff;border:1px solid #E3E7F0'>{nonb} students onboard</span>",
                    unsafe_allow_html=True)
        bus_cards(open_runs)
        st.write("")
    pos = bus_positions(D)
    stops = [{"lat": s["lat"], "lon": s["lon"], "name": s["name"]} for s in db.q("SELECT name, lat, lon FROM stops")]
    st.caption("Bus positions come from the latest scan with GPS (demo). In production they come live from the Autotrace/FVTS GPS units.")
    bus_map(pos, stops)
    tbl = R.r_trip_summary({"d1": D, "d2": D})
    if tbl.empty:
        st.info("No trips on this date. Crew start trips from the Crew app; demo data can be generated in Setup → Demo tools.")
        return
    st.dataframe(tbl, hide_index=True, width="stretch", key="live_tbl", on_select="rerun", selection_mode="single-row")


board()

st.subheader("Trip detail")
runs = db.q("SELECT r.id, r.trip_no, r.status, b.bus_no FROM trip_runs r JOIN buses b ON b.id=r.bus_id WHERE r.date=? ORDER BY r.trip_no, b.bus_no", (D,))
try:
    sel = st.session_state["live_tbl"]["selection"]["rows"]
except (KeyError, TypeError):
    sel = []
default = None
if sel:
    tbl = R.r_trip_summary({"d1": D, "d2": D})
    if sel[0] < len(tbl):
        default = int(tbl.iloc[sel[0]]["Run"])
ids = [r["id"] for r in runs]
if ids:
    rid = st.selectbox("Trip", ids, index=ids.index(default) if default in ids else 0,
                       format_func=lambda i: next(f"{r['bus_no']} · Trip {r['trip_no']} · {r['status']}" for r in runs if r["id"] == i))
    run = E.get_run(rid)
    gps = lambda a, b: f"{a:.5f}, {b:.5f}" if a is not None and b is not None else "no GPS"
    st.caption(f"{TRIPS[run['trip_no']]['label']}")
    cA, cB = st.columns(2)
    cA.markdown(f"**Start** {run['start_ts'] or '—'} · GPS {gps(run['start_lat'], run['start_lon'])}  \n"
                f"Crew at start: {db.staff_name(run['driver_id'])} / {db.staff_name(run['supervisor_id'])} / {db.staff_name(run['caretaker_id'])}")
    cB.markdown(f"**End** {run['end_ts'] or '— (trip open)'} · GPS {gps(run['end_lat'], run['end_lon']) if run['end_ts'] else '—'}  \n"
                f"Final crew: {' / '.join(db.staff_name(x) for x in (run['final_driver_id'], run['final_supervisor_id'], run['final_caretaker_id'])) if run['final_driver_id'] else '—'}"
                f" · Sweep by {run['sweep_by'] or '—'} {(run['sweep_ts'] or '')[11:16]}")
    tab1, tab2 = st.tabs(["Children", "Scan events"])
    with tab1:
        lines_table(E.run_lines(rid), ("name", "code", "class", "batch", "grp", "purpose", "stop_name", "status", "entry_ts", "exit_ts", "handover",
                                       "recipient_name", "received_by", "note"))
    with tab2:
        st.dataframe(pd.DataFrame(db.q("""SELECT e.captured_ts AS Captured, e.received_ts AS Received, e.kind AS Action, s.name AS Student,
            e.result AS Result, e.reason AS Detail, e.lat AS Lat, e.lon AS Lon, e.accuracy AS "Acc. m", e.method AS Method, e.operator AS Operator,
            e.connectivity AS Net, e.sync_state AS Sync FROM events e LEFT JOIN students s ON s.id=e.student_id WHERE e.run_id=? ORDER BY e.captured_ts""",
                                          (rid,))), hide_index=True, width="stretch")
