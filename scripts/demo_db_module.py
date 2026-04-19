"""数据库模块最小可运行示例。"""

import os
import sys
from datetime import date, datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import MedicalRecordRepository, PatientRepository, VisitRepository, init_database  # noqa: E402


def main():
    _, session_factory = init_database()

    with session_factory() as session:
        patient_repo = PatientRepository(session)
        record_repo = MedicalRecordRepository(session)
        visit_repo = VisitRepository(session)

        patient = patient_repo.get_by_patient_no("P0001")
        if patient is None:
            patient = patient_repo.create_patient(
                patient_no="P0001",
                name="张三",
                gender="男",
                birth_date=date(1990, 1, 1),
                phone="13800000000",
                id_card="310101199001010011",
            )
        else:
            patient = patient_repo.update_patient(
                patient.id,
                name="张三",
                gender="男",
                birth_date=date(1990, 1, 1),
                phone="13800000000",
                id_card="310101199001010011",
            )

        latest_record = record_repo.get_latest_by_patient(patient.id)
        if latest_record is None:
            latest_record = record_repo.create_record(
                patient_id=patient.id,
                diagnosis="上呼吸道感染",
                chief_complaint="咳嗽、咽痛 3 天",
                present_illness="近期熬夜后症状加重。",
                doctor_name="李医生",
                department="呼吸内科",
                record_date=date.today(),
            )
        else:
            latest_record = record_repo.update_record(
                latest_record.id,
                diagnosis="上呼吸道感染",
                chief_complaint="咳嗽、咽痛 3 天",
                present_illness="近期熬夜后症状加重。",
                doctor_name="李医生",
                department="呼吸内科",
                record_date=date.today(),
            )

        visit = visit_repo.get_by_visit_no("V0001")
        if visit is None:
            visit = visit_repo.create_visit(
                patient_id=patient.id,
                visit_no="V0001",
                visit_time=datetime.utcnow(),
                department="呼吸内科",
                doctor_name="李医生",
                status="已完成",
                complaint="咳嗽、发热",
                diagnosis_summary="考虑病毒感染可能性较大",
                treatment_plan="注意休息，多饮水，如发热持续请及时复诊。",
            )
        else:
            visit = visit_repo.update_visit(
                visit.id,
                visit_time=datetime.utcnow(),
                department="呼吸内科",
                doctor_name="李医生",
                status="已完成",
                complaint="咳嗽、发热",
                diagnosis_summary="考虑病毒感染可能性较大",
                treatment_plan="注意休息，多饮水，如发热持续请及时复诊。",
            )

        latest_record = record_repo.get_latest_by_patient(patient.id)
        latest_visit = visit_repo.get_latest_by_patient(patient.id)

        print("患者编号: {0} / 患者姓名: {1}".format(patient.patient_no, patient.name))
        print("最新病历诊断: {0}".format(latest_record.diagnosis if latest_record else "无"))
        print("最新就诊状态: {0}".format(latest_visit.status if latest_visit else "无"))


if __name__ == "__main__":
    main()
