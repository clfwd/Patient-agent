import unittest
from datetime import date, datetime

from app.db.database import build_engine, build_session_factory, create_all_tables
from app.db.repositories import MedicalRecordRepository, PatientRepository, VisitRepository


class RepositoryRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.engine = build_engine("sqlite:///:memory:")
        create_all_tables(self.engine)
        self.session_factory = build_session_factory(self.engine)
        self.session = self.session_factory()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_patient_record_and_visit_round_trip(self):
        patient_repo = PatientRepository(self.session)
        record_repo = MedicalRecordRepository(self.session)
        visit_repo = VisitRepository(self.session)

        patient = patient_repo.create_patient(
            patient_no="P10001",
            name="李四",
            gender="女",
            birth_date=date(1988, 6, 5),
            phone="13900000000",
            id_card="320101198806050022",
        )

        fetched_patient = patient_repo.get_by_patient_no("P10001")
        self.assertIsNotNone(fetched_patient)
        self.assertEqual(fetched_patient.name, "李四")

        record = record_repo.create_record(
            patient_id=patient.id,
            diagnosis="高血压",
            chief_complaint="偶发头晕",
            record_date=date(2026, 4, 19),
            department="心内科",
        )
        visit = visit_repo.create_visit(
            patient_id=patient.id,
            visit_no="V10001",
            visit_time=datetime(2026, 4, 19, 9, 30, 0),
            department="心内科",
            status="已完成",
            diagnosis_summary="血压偏高",
        )

        latest_record = record_repo.get_latest_by_patient(patient.id)
        latest_visit = visit_repo.get_by_visit_no("V10001")

        self.assertEqual(record.id, latest_record.id)
        self.assertEqual(visit.id, latest_visit.id)
        self.assertEqual(latest_visit.department, "心内科")

    def test_search_records_and_visits_with_filters(self):
        patient_repo = PatientRepository(self.session)
        record_repo = MedicalRecordRepository(self.session)
        visit_repo = VisitRepository(self.session)

        patient = patient_repo.create_patient(
            patient_no="P10002",
            name="赵敏",
            gender="女",
            birth_date=date(1991, 8, 12),
            phone="13800000001",
            id_card="320101199108120024",
        )

        record_repo.create_record(
            patient_id=patient.id,
            record_type="outpatient",
            diagnosis="踝关节扭伤",
            department="骨科",
            doctor_name="王医生",
            record_date=date(2026, 4, 20),
        )
        record_repo.create_record(
            patient_id=patient.id,
            record_type="followup",
            diagnosis="踝关节扭伤恢复期",
            department="骨科",
            doctor_name="王医生",
            record_date=date(2026, 4, 27),
        )

        visit_repo.create_visit(
            patient_id=patient.id,
            visit_no="V10002",
            visit_time=datetime(2026, 4, 20, 9, 0, 0),
            department="骨科",
            doctor_name="王医生",
            status="已完成",
        )
        visit_repo.create_visit(
            patient_id=patient.id,
            visit_no="V10003",
            visit_time=datetime(2026, 4, 27, 10, 30, 0),
            department="骨科",
            doctor_name="王医生",
            status="已完成",
        )

        records = record_repo.search_records(
            patient_id=patient.id,
            diagnosis_keyword="恢复期",
            date_from=date(2026, 4, 27),
            date_to=date(2026, 4, 27),
            limit=5,
        )
        visits = visit_repo.search_visits(
            patient_id=patient.id,
            visit_no="V10003",
            date_from=datetime(2026, 4, 27, 0, 0, 0),
            date_to=datetime(2026, 4, 27, 23, 59, 59),
            limit=5,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].diagnosis, "踝关节扭伤恢复期")
        self.assertEqual(len(visits), 1)
        self.assertEqual(visits[0].visit_no, "V10003")
