import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict
from django.utils.timezone import make_aware
from django.db import transaction
from hr.models import Employee
from attendance.models import Attendance

class BiometricSyncService:
    API_URL = "https://subscript-crablike-tantrum.ngrok-free.dev/webapiservice.asmx"
    # Ideally these would be stored in settings.py, hardcoding per your example
    SERIAL_NUMBER = "ZHM2242500091"
    USERNAME = "hrms"
    USER_PASSWORD = "Hrms@123!"

    @staticmethod
    def sync_attendance(from_datetime, to_datetime):
        """
        Sync attendance from biometric machine for given date range.
        Dates should be string in 'YYYY-MM-DD HH:MM' format or datetime objects.
        """
        if isinstance(from_datetime, datetime):
            from_datetime = from_datetime.strftime('%Y-%m-%d %H:%M')
        if isinstance(to_datetime, datetime):
            to_datetime = to_datetime.strftime('%Y-%m-%d %H:%M')

        # 1. Fetch data from API
        soap_request = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetTransactionsLog xmlns="http://tempuri.org/">
      <FromDateTime>{from_datetime}</FromDateTime>
      <ToDateTime>{to_datetime}</ToDateTime>
      <SerialNumber>{BiometricSyncService.SERIAL_NUMBER}</SerialNumber>
      <UserName>{BiometricSyncService.USERNAME}</UserName>
      <UserPassword>{BiometricSyncService.USER_PASSWORD}</UserPassword>
      <strDataList>1</strDataList>
    </GetTransactionsLog>
  </soap:Body>
</soap:Envelope>"""

        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'http://tempuri.org/GetTransactionsLog'
        }

        try:
            response = requests.post(BiometricSyncService.API_URL, data=soap_request, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            return {"status": "error", "message": f"API Request failed: {str(e)}"}

        # 2. Parse XML Response
        try:
            root = ET.fromstring(response.content)
            # Find the strDataList element handling the namespace
            namespace = {'tempuri': 'http://tempuri.org/'}
            str_data_list_elem = root.find('.//tempuri:strDataList', namespace)
            
            if str_data_list_elem is None or not str_data_list_elem.text:
                return {"status": "success", "message": "No transaction logs found for the given period.", "synced": 0}
                
            raw_data = str_data_list_elem.text
        except ET.ParseError:
            return {"status": "error", "message": "Failed to parse XML response from API."}

        # 3. Process the logs
        # Dictionary format: { biometric_id: { date_obj: [datetime_obj1, datetime_obj2, ...] } }
        employee_logs = defaultdict(lambda: defaultdict(list))
        
        for line in raw_data.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
                
            parts = line.split('\t')
            if len(parts) >= 2:
                bio_id = parts[0].strip()
                datetime_str = parts[1].strip()
                
                try:
                    dt_obj = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                    # Group by biometric_id and date
                    employee_logs[bio_id][dt_obj.date()].append(dt_obj)
                except ValueError:
                    continue

        # 4. Update the DB
        synced_count = 0
        missing_employees = set()
        
        with transaction.atomic():
            for bio_id, dates_dict in employee_logs.items():
                employee = Employee.objects.filter(biometric_id=bio_id).first()
                if not employee:
                    missing_employees.add(bio_id)
                    continue
                    
                for date_obj, times in dates_dict.items():
                    times.sort()
                    check_in_time = make_aware(times[0]) if times else None
                    # If there's more than one log, the last one is checkout, otherwise None
                    check_out_time = make_aware(times[-1]) if len(times) > 1 else None
                    
                    if not check_in_time:
                        continue
                        
                    # Prioritize biometric data: overwrite check_in.
                    # But don't overwrite a web check_out with None if biometric only has one punch.
                    defaults = {'check_in': check_in_time}
                    
                    existing_attendance = Attendance.objects.filter(employee=employee, date=date_obj).first()
                    
                    if check_out_time:
                        # Biometric has a checkout, prioritize it
                        defaults['check_out'] = check_out_time
                    elif existing_attendance and existing_attendance.check_out:
                        # Biometric has NO checkout, but DB already has one (e.g., Web Checkout). Keep it!
                        pass 
                    else:
                        defaults['check_out'] = None

                    # Update or Create Attendance
                    attendance, created = Attendance.objects.update_or_create(
                        employee=employee,
                        date=date_obj,
                        defaults=defaults
                    )
                    synced_count += 1

                    # ── Auto-restore leave if employee physically attended on a leave day ──
                    # If biometric recorded attendance (check_in exists), cancel any approved
                    # paid leave that covers this date and restore the balance.
                    if check_in_time:
                        from leave.models import Leave
                        from leave.services import LeaveValidationService
                        overlapping_leaves = Leave.objects.filter(
                            employee=employee,
                            status='approved',
                            is_unpaid=False,
                            start_date__lte=date_obj,
                            end_date__gte=date_obj,
                        ).exclude(leave_type__name__icontains='unpaid')

                        for leave in overlapping_leaves:
                            days = leave.days_requested or 1
                            restored = LeaveValidationService.restore_leave_balance(
                                employee, leave.leave_type, days, leave.start_date.year
                            )
                            if restored:
                                leave.status = 'rejected'
                                leave.rejection_reason = 'Auto-cancelled: biometric attendance recorded on leave day.'
                                leave.save()
                                print(f"[AUTO-RESTORE] {employee.first_name} attended on {date_obj} "
                                      f"(leave day). Restored {days} days of {leave.leave_type.name}.")
                    
        return {
            "status": "success",
            "message": f"Successfully synced {synced_count} attendance records.",
            "synced": synced_count,
            "missing_biometric_ids": list(missing_employees)
        }
