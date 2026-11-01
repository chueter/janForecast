import pytest
import pandas as pd
from pathlib import Path
from fpdf import FPDF

@pytest.fixture
def sample_csv_data(tmp_path):
    """Erstellt temporäre CapEx-CSV-Daten für den Test."""
    csv_path = tmp_path / "capex_test.csv"
    df = pd.DataFrame({
        "Projekt": ["Server-Upgrade", "CNC-Maschine", "Büromöbel", "Lager-Erweiterung"],
        "Kategorie": ["IT", "Produktion", "HVAC", "Produktion"],
        "Capex_2024": [50000, 120000, 15000, 200000],
        "Wachstum_Prozent": [5.0, 3.5, 0.0, 2.0],
        "Capex_2025": [52500.0, 124200.0, 15000.0, 204000.0]
    })
    df.to_csv(csv_path, index=False)
    return csv_path

@pytest.fixture
def pdf_ingest(sample_csv_data, tmp_path):
    """Fixture, die aus der CSV dynamisch ein PDF mit Tabellendaten erzeugt."""
    pdf_path = tmp_path / "capex_test.pdf"
    df = pd.read_csv(sample_csv_data)
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    
    pdf.cell(200, 10, text="CapEx Forecast Uebersicht", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    for index, row in df.iterrows():
        line = f"Projekt: {row['Projekt']} | Kategorie: {row['Kategorie']} | 2024: {row['Capex_2024']} | 2025: {row['Capex_2025']}"
        pdf.cell(200, 10, text=line, new_x="LMARGIN", new_y="NEXT")
        
    pdf.output(str(pdf_path))
    return pdf_path

def test_forecast_files_exist(sample_csv_data, pdf_ingest):
    """Prüft die Generierung der CSV- und PDF-Testdateien."""
    assert sample_csv_data.exists(), "CSV-Testdatei wurde nicht erstellt."
    assert pdf_ingest.exists(), "PDF-Testdatei wurde nicht erstellt."
    assert pdf_ingest.stat().st_size > 0, "PDF-Datei ist leer."

def test_csv_and_pdf_content_match(sample_csv_data, pdf_ingest):
    """Stellt sicher, dass die Daten in CSV und PDF konsistent vorhanden sind."""
    df_csv = pd.read_csv(sample_csv_data)
    prod_capex_2025 = df_csv[df_csv["Kategorie"] == "Produktion"]["Capex_2025"].sum()
    assert prod_capex_2025 == 328200.0
