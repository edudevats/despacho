from pathlib import Path

from app import find_company_invoice_xml_path


def test_find_company_invoice_xml_path_finds_generated_xml_case_insensitive(tmp_path):
    company_dir = tmp_path / "xml" / "EKU9003173C9"
    company_dir.mkdir(parents=True)
    xml_path = company_dir / "A0000005_88C6CA64-CDB9-53D8-B75B-E0886730A838.xml"
    xml_path.write_text("<cfdi:Comprobante />", encoding="utf-8")

    found = find_company_invoice_xml_path(
        "EKU9003173C9",
        "88c6ca64-cdb9-53d8-b75b-e0886730a838",
        project_root=str(tmp_path),
    )

    assert Path(found) == xml_path
