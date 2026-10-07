"""Small shared UI helpers."""
import random

import pandas as pd
import pydeck as pdk
import streamlit as st

import db
from engine import STATUS_LABEL
from i18n import t


def msg(level, text):
    icon = {"ok": "✅", "warn": "⚠️", "error": "⛔"}[level]
    st.markdown(f'<div class="{level}">{icon} {text}</div>', unsafe_allow_html=True)


def status_text(s):
    return t(STATUS_LABEL.get(s, s or ""))


def gps_fix(stop_id, unavailable=False):
    """Simulated device GPS: position of the current stop with jitter and an accuracy value."""
    if unavailable:
        return {"lat": None, "lon": None, "accuracy": None, "gps_ok": False}
    stp = db.stop(stop_id)
    return {"lat": stp["lat"] + random.uniform(-.0003, .0003), "lon": stp["lon"] + random.uniform(-.0003, .0003),
            "accuracy": round(random.uniform(4, 18), 1), "gps_ok": True}


def bus_positions(date=None):
    """Last known position per bus = latest accepted event with coordinates on its most recent run (else trip start)."""
    rows = []
    for b in db.buses():
        run = db.q1("SELECT * FROM trip_runs WHERE bus_id=? AND start_ts IS NOT NULL" + (" AND date=?" if date else "") +
                    " ORDER BY start_ts DESC LIMIT 1", (b["id"], date) if date else (b["id"],))
        if not run:
            continue
        ev = db.q1("""SELECT lat, lon, captured_ts, received_ts FROM events WHERE run_id=? AND lat IS NOT NULL AND result<>'REJECTED'
                      ORDER BY captured_ts DESC LIMIT 1""", (run["id"],))
        lat, lon, when = (ev["lat"], ev["lon"], ev["captured_ts"]) if ev else (run["start_lat"], run["start_lon"], run["start_ts"])
        if run["end_ts"] and run["end_lat"]:
            lat, lon, when = run["end_lat"], run["end_lon"], run["end_ts"]
        onboard = db.q1("SELECT COUNT(*) n FROM manifest WHERE run_id=? AND status IN ('ONBOARD','TRANSFER_PENDING')", (run["id"],))["n"]
        rows.append({"bus": b["bus_no"], "bus_id": b["id"], "run_id": run["id"], "trip": run["trip_no"], "status": run["status"],
                     "lat": lat, "lon": lon, "when": when, "onboard": onboard})
    return rows


def bus_map(points, stops=None, height=420, zoom=11.5):
    if not points and not stops:
        return
    df = pd.DataFrame(points)
    layers = []
    if stops:
        sdf = pd.DataFrame(stops)
        layers.append(pdk.Layer("ScatterplotLayer", sdf, get_position="[lon, lat]", get_radius=60, radius_min_pixels=3,
                                get_fill_color=[120, 130, 150, 160], pickable=True))
    if not df.empty:
        df["color"] = df["status"].map(lambda s: [217, 48, 37] if s == "ATTN" else ([30, 142, 62] if s in ("IN_PROGRESS", "PENDING_SYNC")
                                                                                   else [28, 84, 144]))
        df["label"] = df.apply(lambda r: f"{r['bus']} · {r.get('onboard', 0)} on board", axis=1)
        layers.append(pdk.Layer("ScatterplotLayer", df, get_position="[lon, lat]", get_radius=120, radius_min_pixels=8,
                                get_fill_color="color", pickable=True))
        layers.append(pdk.Layer("TextLayer", df, get_position="[lon, lat]", get_text="bus", get_size=13, get_pixel_offset=[0, -18],
                                get_color=[20, 20, 20]))
    lat, lon = db.school_pos()
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom),
                             map_style="light", tooltip={"text": "{label}{name}"}), height=height)


def lines_table(lines, cols=("name", "class", "batch", "grp", "purpose", "stop_name", "status", "entry_ts", "exit_ts", "handover"),
                highlight=None):
    """highlight: set of manifest line ids to mark (children to act on at the selected stop) — shown first, tinted and with 📍."""
    if not lines:
        st.caption("—")
        return
    names = {"name": t("Student"), "code": "ID", "class": t("Class"), "batch": t("Batch"), "grp": t("Group"), "purpose": t("Purpose"), "stop_name": t("Stop"),
             "status": t("Status"), "entry_ts": t("Boarded"), "exit_ts": t("Got off"), "handover": t("Handover"),
             "recipient_name": t("Handed to"), "received_by": t("Received by"), "note": t("Note")}
    hl = set(highlight or ())
    if hl:
        lines = sorted(lines, key=lambda ln: ln.get("id") not in hl)
    df = pd.DataFrame(lines)
    mark = [ln.get("id") in hl for ln in lines]
    df = df[[c for c in cols if c in df]]
    if "status" in df:
        df["status"] = df["status"].map(status_text)
    for c in ("entry_ts", "exit_ts"):
        if c in df:
            df[c] = df[c].fillna("").str[11:16]
    if "purpose" in df:
        df["purpose"] = df["purpose"].map(lambda v: t((v or "").title()))
    if "stop_name" in df:
        df["stop_name"] = df["stop_name"].fillna(t("School"))
    df = df.rename(columns=names)
    if hl and any(mark):
        df.insert(0, " ", ["📍" if m else "" for m in mark])
        sty = df.style.apply(lambda row: ["background-color:#FFF4C2;font-weight:600" if mark[row.name] else "" for _ in row], axis=1)
        st.dataframe(sty, hide_index=True, width="stretch")
    else:
        st.dataframe(df, hide_index=True, width="stretch")


def bus_cards(runs):
    """Live trip cards (one per open trip): route progress, movement, on board / capacity, crew, next stop."""
    cards = []
    for r in runs:
        b = db.bus(r["bus_id"])
        lines = db.q("""SELECT m.*, st.name AS stop_name, st.seq FROM manifest m LEFT JOIN stops st ON st.id=m.stop_id WHERE m.run_id=?""", (r["id"],))
        total = len(lines) or 1
        done = sum(1 for ln in lines if ln["status"] not in ("EXPECTED", "ONBOARD", "TRANSFER_PENDING"))
        frac = done / total
        onb = sum(1 for ln in lines if ln["status"] in ("ONBOARD", "TRANSFER_PENDING"))
        exp_ = sum(1 for ln in lines if ln["status"] == "EXPECTED")   # still to board on this trip
        purposes = {ln["purpose"] for ln in lines}
        kind = "Pickup" if purposes == {"PICKUP"} else ("Drop-off" if purposes == {"DROPOFF"} else "Drop-off + pickup")
        movements = sorted({f"Batch {ln['batch']} {ln['grp']} {'pickup' if ln['purpose'] == 'PICKUP' else 'drop-off'}" for ln in lines})
        area = (b["route_name"] or "").replace("Route ", "")
        if kind == "Pickup":
            ends = (area or "Route", "School")
        else:
            ends = ("School", area or "Route")
        pend = sorted([ln for ln in lines if (ln["status"] == "EXPECTED" and ln["purpose"] == "PICKUP") or
                       (ln["status"] == "ONBOARD" and ln["purpose"] == "DROPOFF")], key=lambda ln: ln["seq"] or 0)
        if any(ln["status"] == "EXPECTED" and ln["purpose"] == "DROPOFF" for ln in lines):
            nxt = "School (boarding)"
        elif pend:
            nxt = pend[0]["stop_name"] or "School"
        elif onb:
            nxt = "School gate"
        else:
            nxt = "Ready to close"
        offline = r["status"] == "PENDING_SYNC"
        pill = "<span class='pill orange'>Offline</span>" if offline else f"<span class='pill'>{kind}</span>"
        cards.append(f"""<div class='bc'><div class='top'><span class='no'>{b['bus_no']}</span><span class='area'>Trip {r['trip_no']}</span>
<span style='margin-left:auto'>{pill}</span></div>
<div class='prog'><div class='f' style='width:{frac * 100:.0f}%'></div><div class='k' style='left:calc({frac * 100:.0f}% - 8px)'></div></div>
<div class='ends'><span>{ends[0]}</span><span>{ends[1]}</span></div>
<div class='grid'><div><div class='l'>Movement</div><div class='v'>{'<br>'.join(movements[:2])}</div></div>
<div><div class='l'>Onboard</div><div class='v'>{onb} / {onb + exp_}</div><div class='l'>{b['capacity']} seats</div></div>
<div><div class='l'>Driver</div><div class='v'>{staff_name(r['driver_id'])}</div></div>
<div><div class='l'>Attendant</div><div class='v'>{staff_name(r['caretaker_id'])}</div></div>
<div><div class='l'>Next</div><div class='v'>{nxt}</div></div>
<div><div class='l'>Progress</div><div class='v'>{done} / {total} done</div></div></div></div>""")
    st.markdown("<div class='buscards'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def staff_name(i):
    return db.staff_name(i) or "—"
