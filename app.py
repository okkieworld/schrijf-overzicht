import os
import psycopg
import streamlit as st
from textwrap import shorten

import os
import streamlit as st

DATABASE_URL = None
try:
    DATABASE_URL = st.secrets["DATABASE_URL"]
except Exception:
    DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    st.error("DATABASE_URL ontbreekt. Zet deze in Streamlit Cloud → Settings → Secrets.")
    st.stop()


def db():
    return psycopg.connect(DATABASE_URL, autocommit=True)

def init_db():
    exec_sql("""
    CREATE TABLE IF NOT EXISTS projects (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        synopsis TEXT DEFAULT ''
    );
    """)

    exec_sql("""
    CREATE TABLE IF NOT EXISTS chapters (
        id SERIAL PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        ord INTEGER NOT NULL DEFAULT 1,
        title TEXT NOT NULL,
        description TEXT DEFAULT ''
    );
    """)

    exec_sql("""
    CREATE TABLE IF NOT EXISTS scenes (
        id SERIAL PRIMARY KEY,
        chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
        ord INTEGER NOT NULL DEFAULT 1,
        title TEXT NOT NULL,
        purpose TEXT DEFAULT '',
        setting TEXT DEFAULT '',
        pov TEXT DEFAULT '',
        conflict TEXT DEFAULT '',
        outcome TEXT DEFAULT '',
        setup TEXT DEFAULT '',
        payoff TEXT DEFAULT '',
        status TEXT DEFAULT 'outline',
        summary TEXT DEFAULT '',
        prose TEXT DEFAULT ''
    );
    """)

def q(sql, params=(), one=False):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone() if one else cur.fetchall()

def exec_sql(sql, params=(), returning_id=False):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if returning_id:
                row = cur.fetchone()
                return row[0] if row else None
    return None

def normalize_order(table, where_col, where_val):
    rows = q(f"SELECT id FROM {table} WHERE {where_col}=%s ORDER BY ord, id", (where_val,))
    for i, (rid,) in enumerate(rows, start=1):
        exec_sql(f"UPDATE {table} SET ord=%s WHERE id=%s", (i, rid))

def basic_summarize(prose: str) -> str:
    prose = prose.strip()
    if not prose:
        return ""
    # Heel eenvoudige “eerste hulp” samenvatting: eerste 2 alinea’s + inkorten
    parts = [p.strip() for p in prose.split("\n\n") if p.strip()]
    pick = "\n\n".join(parts[:2]) if parts else prose
    return shorten(pick.replace("\n", " "), width=320, placeholder="…")

init_db()
st.set_page_config(page_title="Schrijf Overzicht", layout="wide")

st.title("Schrijf Overzicht Dirk Wajer")
if "chapter_form_open" not in st.session_state:
    st.session_state.chapter_form_open = False

if "chapter_id" not in st.session_state:
    st.session_state.chapter_id = None

if "scene_form_open" not in st.session_state:
    st.session_state.scene_form_open = False

if "scene_id" not in st.session_state:
    st.session_state.scene_id = None

if "prev_chapter_id" not in st.session_state:
    st.session_state.prev_chapter_id = None


# Onthoud selectie in de sessie


# Sidebar: project kiezen/maken
st.sidebar.header("Project")
projects = q("SELECT id, title FROM projects ORDER BY id DESC")
proj_titles = ["(nieuw project)"] + [p[1] for p in projects]
choice = st.sidebar.selectbox("Kies project", proj_titles, index=0)

if choice == "(nieuw project)":
    with st.sidebar.form("new_project"):
        title = st.text_input("Titel")
        synopsis = st.text_area("Synopsis", height=120)
        ok = st.form_submit_button("Maak project")
    if ok and title.strip():
        pid = exec_sql("INSERT INTO projects(title, synopsis) VALUES(%s,%s) RETURNING id", (title.strip(), synopsis), returning_id=True)
        st.success("Project aangemaakt.")
        st.rerun()
    st.stop()

project_id = projects[proj_titles.index(choice)-1][0]
project = q("SELECT title, synopsis FROM projects WHERE id=%s", (project_id,), one=True)

# Sidebar: hoofdstukken-navigatie
st.sidebar.subheader("Hoofdstukken")
sidebar_chapters = q(
    "SELECT id, ord, title FROM chapters WHERE project_id=%s ORDER BY ord, id",
    (project_id,)
)

if sidebar_chapters:
    for cid, cord, ctitle in sidebar_chapters:
        active = (st.session_state.chapter_id == cid)
        label = f"{cord:02d} — {ctitle}" + ("  ✅" if active else "")
        if st.sidebar.button(label, key=f"nav_ch_{cid}"):
            st.session_state.chapter_id = cid
            st.rerun()
else:
    st.sidebar.caption("Nog geen hoofdstukken.")
colA, colB = st.columns([1,1])
with colA:
    st.subheader(project[0])
with colB:
    if st.button("Project verwijderen", type="secondary"):
        exec_sql("DELETE FROM projects WHERE id=%s", (project_id,))
        st.rerun()

syn = st.text_area("Project-synopsis", value=project[1] or "", height=140)
if st.button("Synopsis opslaan"):
    exec_sql("UPDATE projects SET synopsis=%s WHERE id=%s", (syn, project_id))
    st.toast("Opgeslagen")

st.divider()

# Hoofdstukken
st.header("Hoofdstukken")
chapters = q("SELECT id, ord, title, description FROM chapters WHERE project_id=%s ORDER BY ord, id", (project_id,))

# (optioneel) knop om het formulier open te zetten
if st.button("➕ Nieuw hoofdstuk maken"):
    st.session_state.chapter_form_open = True
    st.rerun()

with st.expander("➕ Nieuw hoofdstuk", expanded=st.session_state.chapter_form_open):
    with st.form("new_chapter", clear_on_submit=True):
        ctitle = st.text_input("Titel", key="ctitle")
        cdesc = st.text_area("Hoofdstuk-omschrijving", height=100, key="cdesc")
        ok = st.form_submit_button("Toevoegen")

    if ok and ctitle.strip():
        next_ord = (max([c[1] for c in chapters]) + 1) if chapters else 1
        new_cid = exec_sql(
            "INSERT INTO chapters(project_id, ord, title, description) VALUES(%s,%s,%s,%s) RETURNING id",
            (project_id, next_ord, ctitle.strip(), cdesc),
            returning_id=True
        )

        st.session_state.chapter_id = new_cid
        st.session_state.chapter_form_open = False
        st.rerun()


if not chapters:
    st.info("Nog geen hoofdstukken. Voeg er één toe.")
    st.stop()

chap_opts = [f"{ord_:02d} — {title}" for (_id, ord_, title, _d) in chapters]
chapter_ids = [cid for (cid, _ord, _title, _d) in chapters]

# Bepaal welke hoofdstuk-index actief moet zijn
default_idx = 0
if st.session_state.chapter_id in chapter_ids:
    default_idx = chapter_ids.index(st.session_state.chapter_id)

chap_idx = st.selectbox(
    "Selecteer hoofdstuk",
    list(range(len(chap_opts))),
    format_func=lambda i: chap_opts[i],
    index=default_idx,
    key="chapter_selectbox"
)

chapter_id, chapter_ord, chapter_title, chapter_desc = chapters[chap_idx]
st.session_state.chapter_id = chapter_id  # sync terug

# Detecteer hoofdstukwissel en reset scène-selectie
if st.session_state.prev_chapter_id is None:
    st.session_state.prev_chapter_id = chapter_id
elif st.session_state.prev_chapter_id != chapter_id:
    st.session_state.prev_chapter_id = chapter_id
    st.session_state.scene_id = None
    st.session_state.scene_form_open = False
    if "scene_selectbox" in st.session_state:
        del st.session_state["scene_selectbox"]
    st.rerun()

c1, c2, c3 = st.columns([2,1,1])
with c1:
    new_title = st.text_input("Hoofdstuktitel", value=chapter_title)
with c2:
    new_ord = st.number_input(
    "Volgorde",
    min_value=1,
    value=chapter_ord,
    step=1,
    key=f"chapter_ord_{chapter_id}"
)
with c3:
    if st.button("Hoofdstuk verwijderen"):
        exec_sql("DELETE FROM chapters WHERE id=%s", (chapter_id,))
        normalize_order("chapters", "project_id", project_id)
        st.rerun()

new_desc = st.text_area("Hoofdstuk-omschrijving", value=chapter_desc or "", height=120)
if st.button("Hoofdstuk opslaan"):
    exec_sql("UPDATE chapters SET title=%s, ord=%s, description=%s WHERE id=%s",
             (new_title.strip() or chapter_title, int(new_ord), new_desc, chapter_id))
    normalize_order("chapters", "project_id", project_id)
    st.rerun()

st.divider()

# Scènes
st.header("Scènes in dit hoofdstuk")
scenes = q("""
SELECT id, ord, title, status, summary
FROM scenes
WHERE chapter_id=%s
ORDER BY ord, id
""", (chapter_id,))

if st.button("➕ Nieuwe scène maken"):
    st.session_state.scene_form_open = True
    st.rerun()


with st.expander("➕ Nieuwe scène", expanded=st.session_state.scene_form_open):
    with st.form("new_scene", clear_on_submit=True):
        stitle = st.text_input("Titel", key="stitle")
        status = st.selectbox("Status", ["idea", "outline", "draft", "done"], index=1, key="sstatus")
        ok = st.form_submit_button("Toevoegen")

    if ok and stitle.strip():
        next_ord = (max([s[1] for s in scenes]) + 1) if scenes else 1
        new_sid = exec_sql(
            "INSERT INTO scenes(chapter_id, ord, title, status) VALUES(%s,%s,%s,%s) RETURNING id",
            (chapter_id, next_ord, stitle.strip(), status),
            returning_id=True
        )

        st.session_state.scene_id = new_sid
        st.session_state.scene_form_open = False
        st.rerun()

if not scenes:
    st.info("Nog geen scènes in dit hoofdstuk.")
    st.stop()

scene_opts = [f"{ord_:02d} — {title} [{status}]" for (_id, ord_, title, status, _sum) in scenes]

scene_ids = [sid for (sid, _o, _t, _s, _sm) in scenes]

default_scene_idx = 0
if st.session_state.scene_id in scene_ids:
    default_scene_idx = scene_ids.index(st.session_state.scene_id)

scene_idx = st.selectbox(
    "Selecteer scène",
    list(range(len(scene_opts))),
    format_func=lambda i: scene_opts[i],
    index=default_scene_idx,
    key="scene_selectbox"
)

scene_id, scene_ord, scene_title, scene_status, scene_summary = scenes[int(scene_idx)]
st.session_state.scene_id = scene_id

scene = q("""
SELECT title, ord, status, purpose, setting, pov, conflict, outcome, setup, payoff, summary, prose
FROM scenes WHERE id=%s
""", (scene_id,), one=True)

(title, ord_, status, purpose, setting, pov, conflict, outcome, setup, payoff, summary, prose) = scene

left, right = st.columns([1,1])


with left:
    st.subheader("Scènekaart")
    tcol1, tcol2, tcol3 = st.columns([2,1,1])
    with tcol1:
        title2 = st.text_input("Titel", value=title)
    with tcol2:
        ord2 = st.number_input(
    "Volgorde",
    min_value=1,
    value=int(ord_),
    step=1,
    key=f"scene_ord_{scene_id}"
)
    with tcol3:
        status2 = st.selectbox("Status", ["idea", "outline", "draft", "done"],
                               index=["idea","outline","draft","done"].index(status))

    purpose2 = st.text_area("Functie / wat verandert er%s", value=purpose or "", height=80)
    setting2 = st.text_input("Setting / tijd", value=setting or "")
    pov2 = st.text_input("POV", value=pov or "")
    conflict2 = st.text_area("Conflict", value=conflict or "", height=80)
    outcome2 = st.text_area("Uitkomst", value=outcome or "", height=80)
    setup2 = st.text_area("Setup (zet klaar voor later)", value=setup or "", height=80)
    payoff2 = st.text_area("Payoff (wordt later ingelost)", value=payoff or "", height=80)

    summary2 = st.text_area("Scènesamenvatting (bewerken mag)", value=summary or "", height=110)

    b1, b2, b3 = st.columns([1,1,1])
    with b1:
        if st.button("Scène opslaan"):
            exec_sql("""
            UPDATE scenes SET
                title=%s, ord=%s, status=%s, purpose=%s, setting=%s, pov=%s, conflict=%s, outcome=%s,
                setup=%s, payoff=%s, summary=%s
            WHERE id=%s
            """, (title2.strip() or title, int(ord2), status2, purpose2, setting2, pov2,
                  conflict2, outcome2, setup2, payoff2, summary2, scene_id))
            normalize_order("scenes", "chapter_id", chapter_id)
            st.rerun()
    with b2:
        if st.button("Samenvat uit proza"):
            new_sum = basic_summarize(prose or "")
            exec_sql("UPDATE scenes SET summary=%s WHERE id=%s", (new_sum, scene_id))
            st.rerun()
    with b3:
        if st.button("Scène verwijderen"):
            exec_sql("DELETE FROM scenes WHERE id=%s", (scene_id,))
            normalize_order("scenes", "chapter_id", chapter_id)
            st.rerun()

with right:
    st.subheader("Proza (per scène)")
    prose2 = st.text_area(
        "Tekst",
        value=prose or "",
        height=750,
        key=f"prose_text_{scene_id}"
    )
    if st.button("Proza opslaan"):
        exec_sql("UPDATE scenes SET prose=%s WHERE id=%s", (prose2, scene_id))
        st.toast("Proza opgeslagen")

st.divider()

# Mini-overzicht: alle scènes in hoofdstuk
scenes_scan = q("""
SELECT id, ord, title, status, pov, setting, summary
FROM scenes
WHERE chapter_id=%s
ORDER BY ord, id
""", (chapter_id,))

st.subheader("Overzicht (snelle scan)")
for sid, o, t, status, pov, setting, sm in scenes_scan:
    meta_parts = [status]

    if pov:
        meta_parts.append(f"POV: {pov}")

    if setting:
        meta_parts.append(setting)  # bijv. "Bibliotheek - Nacht"

    meta_line = " | ".join(meta_parts)

    st.markdown(f"**{o:02d} — {t}**  \n_{meta_line}_")

    if (sm or "").strip():
        st.write(sm)
    else:
        st.caption("— geen samenvatting —")

    st.divider()





















