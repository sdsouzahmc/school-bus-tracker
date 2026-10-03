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


def lines_table(lines, cols=("name", "class", "batch", "grp", "purpose", "stop_name", "status", "entry_ts", "exit_ts", "handover")):
    if not lines:
        st.caption("—")
        return
    names = {"name": t("Student"), "code": "ID", "class": t("Class"), "batch": t("Batch"), "grp": t("Group"), "purpose": t("Purpose"), "stop_name": t("Stop"),
             "status": t("Status"), "entry_ts": t("Boarded"), "exit_ts": t("Got off"), "handover": t("Handover"),
             "recipient_name": t("Handed to"), "received_by": t("Received by"), "note": t("Note")}
    df = pd.DataFrame(lines)
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
    st.dataframe(df.rename(columns=names), hide_index=True, width="stretch")
