import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class PatientApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("sqlite:///:memory:")
        self.client = TestClient(self.app)

    def test_patient_record_and_visit_api_flow(self):
        health_response = self.client.get("/health")
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.json()["status"], "ok")

        patient_response = self.client.post(
            "/api/v1/patients",
            json={
                "patient_no": "P20001",
                "name": "王五",
                "gender": "男",
                "phone": "13700000000",
                "id_card": "110101199001011234",
            },
        )
        self.assertEqual(patient_response.status_code, 200)
        patient = patient_response.json()
        self.assertEqual(patient["patient_no"], "P20001")

        record_response = self.client.post(
            "/api/v1/patients/{0}/medical-records".format(patient["id"]),
            json={
                "record_type": "outpatient",
                "diagnosis": "感冒",
                "chief_complaint": "咳嗽两天",
            },
        )
        self.assertEqual(record_response.status_code, 200)
        record = record_response.json()

        visit_response = self.client.post(
            "/api/v1/patients/{0}/visits".format(patient["id"]),
            json={
                "visit_no": "V20001",
                "visit_type": "outpatient",
                "visit_time": "2026-04-19T10:30:00",
                "department": "呼吸内科",
                "status": "已完成",
            },
        )
        self.assertEqual(visit_response.status_code, 200)
        visit = visit_response.json()

        patient_detail = self.client.get("/api/v1/patients/{0}".format(patient["id"]))
        patient_list = self.client.get("/api/v1/patients")
        patient_search = self.client.get("/api/v1/patients?patient_no=P20001")
        record_list = self.client.get("/api/v1/patients/{0}/medical-records".format(patient["id"]))
        record_detail = self.client.get("/api/v1/medical-records/{0}".format(record["id"]))
        visit_list = self.client.get("/api/v1/patients/{0}/visits".format(patient["id"]))
        visit_detail = self.client.get("/api/v1/visits/{0}".format(visit["id"]))

        self.assertEqual(patient_detail.status_code, 200)
        self.assertEqual(patient_list.status_code, 200)
        self.assertEqual(patient_search.status_code, 200)
        self.assertEqual(record_list.status_code, 200)
        self.assertEqual(record_detail.status_code, 200)
        self.assertEqual(visit_list.status_code, 200)
        self.assertEqual(visit_detail.status_code, 200)
        self.assertEqual(len(patient_list.json()), 1)
        self.assertEqual(len(patient_search.json()), 1)
        self.assertEqual(len(record_list.json()), 1)
        self.assertEqual(len(visit_list.json()), 1)

        patient_update = self.client.patch(
            "/api/v1/patients/{0}".format(patient["id"]),
            json={"address": "上海市浦东新区", "phone": "13711112222"},
        )
        record_update = self.client.patch(
            "/api/v1/medical-records/{0}".format(record["id"]),
            json={"notes": "建议多休息"},
        )
        visit_update = self.client.patch(
            "/api/v1/visits/{0}".format(visit["id"]),
            json={"status": "复诊待安排"},
        )

        self.assertEqual(patient_update.status_code, 200)
        self.assertEqual(record_update.status_code, 200)
        self.assertEqual(visit_update.status_code, 200)
        self.assertEqual(patient_update.json()["address"], "上海市浦东新区")
        self.assertEqual(record_update.json()["notes"], "建议多休息")
        self.assertEqual(visit_update.json()["status"], "复诊待安排")

        duplicate_patient = self.client.post(
            "/api/v1/patients",
            json={
                "patient_no": "P20001",
                "name": "重复患者",
            },
        )
        self.assertEqual(duplicate_patient.status_code, 409)

        missing_patient = self.client.get("/api/v1/patients/not-exists")
        missing_record = self.client.get("/api/v1/medical-records/not-exists")
        missing_visit = self.client.get("/api/v1/visits/not-exists")

        self.assertEqual(missing_patient.status_code, 404)
        self.assertEqual(missing_record.status_code, 404)
        self.assertEqual(missing_visit.status_code, 404)
