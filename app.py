import io
import json
import os
import re
import sqlite3
from pathlib import Path

import requests
import streamlit as st

cfg = json.loads(Path(__file__).with_name("project.json").read_text())
roll = cfg["roll"]
st.set_page_config(page_title=cfg["title"], layout="wide")
st.caption(f"GENAI MINI PROJECT  /  ROLL {roll}")
st.title(cfg["title"])
st.write(cfg["goal"])
samples = cfg["samples"]
sample = st.selectbox("Sample input", ["Custom"] + list(samples))
defaults = samples.get(sample, ["", "", ""])
with st.form("input"):
    values = [st.text_area(label, value=defaults[i], key=f"{sample}-{i}") for i, label in enumerate(cfg["fields"])]
    files = st.file_uploader("Upload PDF or TXT invoices", type=["pdf","txt"], accept_multiple_files=True) if roll == 63 else []
    save = st.checkbox("Save this entry locally on this device") if roll == 57 else False
    submitted = st.form_submit_button("Generate result", type="primary")

def call_model(data):
    endpoint = os.getenv("MODEL_URL", "http://127.0.0.1:11434/v1/chat/completions")
    response = requests.post(endpoint, json={
        "model": os.getenv("MODEL_NAME", "qwen2.5:1.5b"),
        "messages": [{"role": "system", "content": cfg["prompt"]},
                     {"role": "user", "content": json.dumps(data, ensure_ascii=False)}],
        "response_format": {"type": "json_object"}, "temperature": 0,
        "max_tokens": 1800,
    }, timeout=150)
    response.raise_for_status()
    result = json.loads(response.json()["choices"][0]["message"]["content"])
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object.")
    return result

HELP = "[14416](tel:+9114416?oai_link_source=model_response_hotline)"
DISTRESS = re.compile(r"suicid|kill myself|hurt myself|self.harm|end my life|don.t want to (?:be alive|live)|can.t go on|hopeless|panic|overwhelmed|unsafe|distress|depress", re.I)
if roll == 57:
    st.info("For reflection and general support. India: Tele-MANAS " + HELP + ". If you may act on thoughts of self-harm or are in immediate danger, contact local emergency services and reach someone you trust now.")
    st.caption("The text is sent to the configured model. Use a local endpoint for private entries. Saved entries are stored unencrypted on this machine.")

def validate(out):
    if roll == 50:
        options = out["options"]
        if not isinstance(options,list) or len(options)!=4 or any(not isinstance(x,str) or not x.strip() for x in options) or len(set(options))!=4 or type(out["answer"]) is not int or not 0<=out["answer"]<4:
            raise ValueError("Expected four distinct options and a valid answer index.")
        assert all(isinstance(out[k],str) and out[k].strip() for k in ("question","solution"))
    elif roll == 64:
        assert len(out["ideas"]) == 10 and len({x["name"].strip().casefold() for x in out["ideas"]}) == 10
        assert all(isinstance(x[k],str) and x[k].strip() for x in out["ideas"] for k in ("name","slogan"))
        assert len(out["pitch"]) == 3 and all(isinstance(x,str) and x.strip() for x in out["pitch"])
    elif roll == 63:
        assert all(k in out for k in ("invoice_number","date","total","items"))
        assert all(out[k] is None or isinstance(out[k],(str,int,float)) for k in ("invoice_number","date","total"))
        assert isinstance(out["items"],list) and all(isinstance(x,dict) and set(x)=={"description","quantity","amount"} and all(v is None or isinstance(v,(str,int,float)) for v in x.values()) for x in out["items"])
    else:
        assert isinstance(out["reply"],str) and out["reply"].strip()
    return out

if submitted:
    st.session_state.pop("result",None)
    st.session_state.pop("favourites",None)
    try:
        with st.spinner("Processing input…"):
            if roll == 63:
                from pypdf import PdfReader
                texts = []
                if values[0].strip():
                    texts.append(values[0])
                if len(files)>5:
                    raise ValueError("Upload at most five files per batch.")
                for f in files:
                    if f.size > 5_000_000:
                        raise ValueError("Each invoice must be under 5 MB.")
                    if f.name.lower().endswith(".pdf"):
                        pdf = PdfReader(f)
                        if len(pdf.pages)>10:
                            raise ValueError("Use PDFs with up to 10 pages.")
                        source = "\n".join(page.extract_text() or "" for page in pdf.pages)
                    else:
                        source = f.getvalue().decode("utf-8-sig")
                    if not source.strip():
                        raise ValueError("No selectable text was found. Apply OCR and paste the text.")
                    texts.append(source)
                if not texts or any(len(t)>12000 for t in texts):
                    raise ValueError("Provide invoice text of at most 12,000 characters per document.")
                result = [validate(call_model(t)) for t in texts]
            else:
                if any(not v.strip() or len(v)>4000 for v in values):
                    raise ValueError("Fill all fields and keep each under 4,000 characters.")
                distress = roll == 57 and bool(DISTRESS.search(values[0]))
                if distress:
                    result = {"reply":"That sounds difficult to carry alone. Can you reach someone you trust and tell them how you’re feeling? A trained counsellor can also help you work through what’s happening.","distress":True}
                else:
                    result = validate(call_model(dict(zip(cfg["fields"],values))))
                if roll == 57 and save:
                    with sqlite3.connect(Path(__file__).with_name("journal.sqlite3")) as db:
                        db.execute("CREATE TABLE IF NOT EXISTS entries (created_at TEXT DEFAULT CURRENT_TIMESTAMP, entry TEXT NOT NULL)")
                        db.execute("INSERT INTO entries(entry) VALUES (?)", (values[0],))
                    st.success("Entry saved locally.")
            st.session_state["result"] = result
    except (ValueError, TypeError, KeyError, AssertionError, requests.RequestException, OSError, sqlite3.Error) as exc:
        st.error(f"Could not process the input. Check the model server or input format. {exc}")
    except Exception as exc:
        if roll != 63:
            raise
        st.error(f"Could not read the invoice: {type(exc).__name__}.")

result = st.session_state.get("result")
if result is not None:
    st.subheader("Result")
    if roll == 50:
        st.write(result["question"])
        choice = st.radio("Choose an answer",result["options"],index=None,key="answer_"+result["question"])
        if choice is not None:
            if choice == result["options"][result["answer"]]:
                st.success("Correct")
            else:
                st.info("Try again or open the solution.")
        with st.expander("Show solution"):
            st.write("Answer: " + result["options"][result["answer"]])
            st.write(result["solution"])
    elif roll == 57:
        if result.get("distress"):
            st.warning("Support is available. Tele-MANAS " + HELP)
        st.write(result["reply"])
    elif roll == 64:
        st.caption("Check trademarks and domains before adopting a name.")
        for line in result["pitch"]:
            st.write(line)
        favourites = st.multiselect("Favourite options", [x["name"] for x in result["ideas"]], key="favourites")
        st.table(result["ideas"])
        st.download_button("Download favourites",json.dumps([x for x in result["ideas"] if x["name"] in favourites],ensure_ascii=False,indent=2),"favourites.json")
    else:
        from openpyxl import Workbook
        book = Workbook()
        invoice_sheet = book.active
        invoice_sheet.title = "Invoices"
        invoice_sheet.append(["Document","Invoice number","Date","Total"])
        items = book.create_sheet("Line items")
        items.append(["Document","Description","Quantity","Amount"])
        def append(sheet, row):
            sheet.append(row)
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value,str):
                    cell.data_type = "s"
        for i, invoice in enumerate(result, 1):
            st.write(f"Invoice {i}")
            summary = {k:invoice[k] for k in ("invoice_number","date","total")}
            st.table([summary])
            if invoice["items"]:
                st.table(invoice["items"])
            append(invoice_sheet,[i,*summary.values()])
            for item in invoice["items"]:
                append(items,[i,item["description"],item["quantity"],item["amount"]])
        with st.expander("View extracted JSON"):
            st.json(result)
        output = io.BytesIO()
        book.save(output)
        st.download_button("Download all invoices (Excel)",output.getvalue(),"invoices.xlsx")
        st.caption("Verify extracted fields and amounts against each original invoice.")
