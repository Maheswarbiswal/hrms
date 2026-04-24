import calendar
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q, Sum
from django.utils import timezone
from datetime import datetime, date
from decimal import Decimal
from hr.models import Department, Employee, Location
from hrms import settings
from leave.models import LeaveBalance, Leave, Holiday
from attendance.models import Attendance
from .models import SalaryComponent, EmployeeSalary, EmployeeSalaryComponent, PayrollRun, Payslip, PayslipComponent
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
from fpdf import FPDF

# Salary Components Views
def get_attendance_stats(employee, year, month):
    from calendar import monthrange
    from datetime import date, timedelta
    
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    today = date.today()
    
    attendances = Attendance.objects.filter(employee=employee, date__range=[first_day, last_day])
    att_dict = {a.date: a for a in attendances}
    
    holidays = Holiday.objects.filter(date__range=[first_day, last_day], region__name__iexact=employee.location)
    holiday_dates = set(h.date for h in holidays)
    
    total_days = (last_day - first_day).days + 1
    working_days = 0 # This will be used as "Paid Days"
    absent_days = 0
    
    for i in range(total_days):
        current_date = first_day + timedelta(days=i)
        if current_date > today:
            continue

        att = att_dict.get(current_date)
        is_holiday = current_date in holiday_dates
        is_sunday = current_date.weekday() == 6
        
        if att:
            if att.check_in and att.check_out:
                diff = att.check_out - att.check_in
                worked_hours = diff.total_seconds() / 3600
                if worked_hours < 2:
                    absent_days += 1
                elif worked_hours < 5:
                    if current_date.weekday() == 5: # Sat
                         working_days += 1
                    elif is_sunday:
                         working_days += 1
                    else:
                         working_days += 0.5
                         absent_days += 0.5
                else:
                    working_days += 1
            elif att.check_in:
                 if current_date.weekday() == 5 or is_sunday:
                      working_days += 1
                 else:
                      working_days += 0.5
                      absent_days += 0.5
            else:
                 if is_holiday or is_sunday:
                      working_days += 1
                 else:
                      absent_days += 1
        else:
            if is_holiday or is_sunday:
                working_days += 1
            else:
                absent_days += 1
    
    return {
        'total_days': total_days,
        'paid_days': working_days,
        'absent_days': absent_days,
    }

def salary_components(request):
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    components = SalaryComponent.objects.all().order_by('component_type', 'name')
    
    # Calculate statistics
    total_count = components.count()
    earning_count = components.filter(component_type='earning').count()
    deduction_count = components.filter(component_type='deduction').count()
    active_count = components.filter(is_active=True).count()
    
    context = {
        'components': components,
        'total_count': total_count,
        'earning_count': earning_count,
        'deduction_count': deduction_count,
        'active_count': active_count,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'payroll/salary_components.html', context)

def add_salary_component(request):
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            component_type = request.POST.get('component_type')
            calculation_type = request.POST.get('calculation_type')
            value = request.POST.get('value', 0) or 0
            formula = request.POST.get('formula', '')
            percentage_of = request.POST.get('percentage_of', '')
            is_taxable = request.POST.get('is_taxable') == 'on'
            
            component = SalaryComponent(
                name=name,
                component_type=component_type,
                calculation_type=calculation_type,
                value=Decimal(value),
                formula=formula,
                percentage_of=percentage_of,
                is_taxable=is_taxable
            )
            component.save()
            
            messages.success(request, f'Salary component "{name}" added successfully!')
            return redirect('salary_components')
            
        except Exception as e:
            messages.error(request, f'Error adding salary component: {str(e)}')
    
    context = {
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'payroll/add_salary_component.html', context)

def edit_salary_component(request, component_id):
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    component = get_object_or_404(SalaryComponent, id=component_id)
    
    if request.method == 'POST':
        try:
            component.name = request.POST.get('name')
            component.component_type = request.POST.get('component_type')
            component.calculation_type = request.POST.get('calculation_type')
            component.value = Decimal(request.POST.get('value', 0) or 0)
            component.formula = request.POST.get('formula', '')
            component.percentage_of = request.POST.get('percentage_of', '')
            component.is_taxable = request.POST.get('is_taxable') == 'on'
            component.save()
            
            messages.success(request, f'Salary component "{component.name}" updated successfully!')
            return redirect('salary_components')
            
        except Exception as e:
            messages.error(request, f'Error updating salary component: {str(e)}')
    
    context = {
        'component': component,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'payroll/edit_salary_component.html', context)

def delete_salary_component(request, component_id):
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    component = get_object_or_404(SalaryComponent, id=component_id)
    
    if request.method == 'POST':
        component_name = component.name
        component.delete()
        messages.success(request, f'Salary component "{component_name}" deleted successfully!')
    
    return redirect('salary_components')

def toggle_salary_component(request, component_id):
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    component = get_object_or_404(SalaryComponent, id=component_id)
    component.is_active = not component.is_active
    component.save()
    
    status = "activated" if component.is_active else "deactivated"
    messages.success(request, f'Salary component "{component.name}" {status} successfully!')
    
    return redirect('salary_components')

# Employee Salaries Views
def employee_salaries(request):
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    salaries = EmployeeSalary.objects.select_related('employee').filter(is_active=True).order_by('-effective_date')
    # Get all active departments for the dropdown
    departments = Department.objects.filter(is_active=True).order_by('name')
    context = {
        'salaries': salaries,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
        'departments': departments,
    }
    return render(request, 'payroll/employee_salaries.html', context)

def add_employee_salary(request):
    if not request.session.get('user_authenticated'):
        return redirect('login')

    employees = Employee.objects.filter(status='active')
    components = SalaryComponent.objects.filter(is_active=True)

    if request.method == 'POST':
        try:
            # Debug: Print all POST data to see what's coming in
            print("=" * 50)
            print("POST DATA RECEIVED:")
            for key, value in request.POST.items():
                print(f"{key}: {value}")
            print("=" * 50)
            
            # Get selected employees from the hidden field
            selected_employee_ids = request.POST.get('selected_employees', '')
            if not selected_employee_ids:
                messages.error(request, 'Please select at least one employee.')
                return redirect('add_employee_salary')
            
            employee_ids = [int(id) for id in selected_employee_ids.split(',') if id]
            effective_date_str = request.POST.get('effective_date')
            
            if not effective_date_str:
                messages.error(request, 'Effective date is required.')
                return redirect('add_employee_salary')
            
            # Convert string → date object
            effective_date = datetime.strptime(effective_date_str, "%Y-%m-%d").date()
            salary_month = effective_date.replace(day=1)
            
            success_count = 0
            error_employees = []
            
            for employee_id in employee_ids:
                try:
                    employee = Employee.objects.get(id=employee_id)
                    
                    # Check if salary already exists for this employee for this month
                    salary_exists = EmployeeSalary.objects.filter(
                        employee=employee,
                        effective_date__year=salary_month.year,
                        effective_date__month=salary_month.month
                    ).exists()
                    
                    if salary_exists:
                        error_employees.append(f"{employee.first_name} {employee.last_name} (already exists for {salary_month.strftime('%B %Y')})")
                        continue
                    
                    # Get basic salary for this employee
                    basic_salary_key = f'employee_{employee_id}_basic_salary'
                    basic_salary = Decimal(request.POST.get(basic_salary_key, 0))
                    
                    # Get earned salary (after unpaid leaves)
                    earned_salary_key = f'employee_{employee_id}_earned_salary'
                    earned_salary = Decimal(request.POST.get(earned_salary_key, basic_salary))
                    
                    # Create new salary record
                    salary = EmployeeSalary.objects.create(
                        employee=employee,
                        effective_date=effective_date,
                        basic_salary=basic_salary,
                        gross_salary=Decimal('0.00'),
                        net_salary=Decimal('0.00'),
                        is_active=True
                    )
                    
                    # Initialize totals
                    total_earnings = Decimal('0.00')
                    total_deductions = Decimal('0.00')
                    
                    # Process each component from the form
                    for component in components:
                        amount_key = f'employee_{employee_id}_component_{component.id}'
                        amount = request.POST.get(amount_key)
                        
                        if amount:
                            amount_decimal = Decimal(amount)
                            if amount_decimal > 0:
                                EmployeeSalaryComponent.objects.create(
                                    employee_salary=salary,
                                    component=component,
                                    amount=amount_decimal,
                                    created_by=request.session.get('user_name', 'system')
                                )
                                
                                if component.component_type == 'earning':
                                    total_earnings += amount_decimal
                                elif component.component_type == 'deduction':
                                    total_deductions += amount_decimal
                    
                    # Get statutory deductions (these might already be included in components)
                    pf_amount = Decimal(request.POST.get(f'employee_{employee_id}_pf', 0))
                    esi_amount = Decimal(request.POST.get(f'employee_{employee_id}_esi', 0))
                    pt_amount = Decimal(request.POST.get(f'employee_{employee_id}_professional_tax', 0))
                    tds_amount = Decimal(request.POST.get(f'employee_{employee_id}_tds', 0))
                   
                    
                    # Check if these statutory deductions are already included in components
                    # to avoid double counting
                    components_list = list(components.values('name', 'component_type'))
                    component_names = [c['name'].upper() for c in components_list]
                    
                    if 'PF' not in component_names and pf_amount > 0:
                        total_deductions += pf_amount
                        # Optionally create component record for PF if needed
                    
                    if 'ESI' not in component_names and esi_amount > 0:
                        total_deductions += esi_amount
                    
                    if 'PT' not in component_names and 'PROFESSIONAL TAX' not in component_names and pt_amount > 0:
                        total_deductions += pt_amount
                    
                    if 'TDS' not in component_names and tds_amount > 0:
                        total_deductions += tds_amount
                    
                    # CRITICAL FIX: Gross Salary = Basic Salary + Total Earnings
                    salary.gross_salary = basic_salary + total_earnings
                    
                    # Net Salary = Gross Salary - Total Deductions
                    salary.net_salary = salary.gross_salary - total_deductions
                    
                    # Save the salary record
                    salary.save()
                    
                    
                    # CRITICAL FIX: Gross Salary = Earned Salary + Total Earnings (NOT including deductions)
                    # salary.gross_salary = earned_salary + total_earnings
                    # print(f"gross_salary: {salary.gross_salary}")
                    # salary.gross_salary= basic_salary + pf_amount + esi_amount + pt_amount
                    # print(f"gross_salary: {salary.gross_salary}")
                    # salary.gross_salary = earned_salary + total_earnings
                    # salary.net_salary = basic_salary + total_earnings - total_deductions







                    
                    
                    success_count += 1
                    
                except Employee.DoesNotExist:
                    error_employees.append(f"Employee ID {employee_id} not found")
                except Exception as e:
                    error_employees.append(f"Error for employee {employee_id}: {str(e)}")
                    print(f"Error details for employee {employee_id}: {e}")
            
            # Show success/error messages
            if success_count > 0:
                messages.success(request, f'Successfully created salary structure for {success_count} employee(s)!')
            
            if error_employees:
                messages.warning(request, f'Failed for: {", ".join(error_employees[:5])}')
            
            return redirect('employee_salaries')
            
        except Exception as e:
            messages.error(request, f'Error creating salary structures: {str(e)}')
            print(f"Major error: {e}")
            return redirect('add_employee_salary')

    locations = Location.objects.filter(is_active=True).order_by('name')
    
    context = {
        'employees': employees,
        'components': components,
        'locations': locations,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'payroll/add_employee_salary.html', context)


def calculate_salary_totals(salary):
    """Calculate gross and net salary based on components"""
    components = EmployeeSalaryComponent.objects.filter(employee_salary=salary).select_related('component')
    
    total_earnings = Decimal('0.00')
    total_deductions = Decimal('0.00')
    
    for comp in components:
        if comp.component.component_type == 'earning':
            total_earnings += comp.amount
        else:
            total_deductions += comp.amount
    
    salary.gross_salary = salary.basic_salary + total_earnings
    salary.net_salary = salary.gross_salary - total_deductions
    salary.save()
    
    return salary

def calculate_salary_api(request):
    """API endpoint for salary calculation"""
    if request.method == 'POST':
        try:
            basic_salary = Decimal(request.POST.get('basic_salary', 0))
            components_data = request.POST.get('components', '{}')
            
            # This would be more complex in real implementation
            # For now, return a simple calculation
            hra = basic_salary * Decimal('0.40')  # 40% HRA
            conveyance = Decimal('1600.00')
            medical = Decimal('1250.00')
            
            total_earnings = hra + conveyance + medical
            gross_salary = basic_salary + total_earnings
            
            # Deductions
            pf = basic_salary * Decimal('0.12')  # 12% PF
            professional_tax = Decimal('200.00')
            total_deductions = pf + professional_tax
            
            net_salary = gross_salary - total_deductions
            
            return JsonResponse({
                'success': True,
                'gross_salary': float(gross_salary),
                'net_salary': float(net_salary),
                'breakdown': {
                    'basic_salary': float(basic_salary),
                    'hra': float(hra),
                    'conveyance': float(conveyance),
                    'medical': float(medical),
                    'pf': float(pf),
                    'professional_tax': float(professional_tax)
                }
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


# payroll/views.py
def payroll_runs(request):
    """List all payroll runs"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    payroll_runs_list = PayrollRun.objects.all().order_by('-payroll_year', '-payroll_month', '-created_at')
    
    total_count = payroll_runs_list.count()
    draft_count = payroll_runs_list.filter(status='draft').count()
    processing_count = payroll_runs_list.filter(status='processing').count()
    completed_count = payroll_runs_list.filter(status='completed').count()
    month_choices = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
    ]
    context = {
        'payroll_runs': payroll_runs_list,
        'total_count': total_count,
        'draft_count': draft_count,
        'processing_count': processing_count,
        'completed_count': completed_count,
        'month_choices': month_choices, 
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'payroll/payroll_runs.html', context)

def create_payroll_run(request):
    """Create a new payroll run - ALLOW multiple runs per month"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            payroll_year = int(request.POST.get('payroll_year'))
            payroll_month = int(request.POST.get('payroll_month'))
            selected_employees = request.POST.getlist('employees')
            
            if not selected_employees:
                messages.error(request, 'Please select at least one employee.')
                return redirect('create_payroll_run')
            
            # Create payroll run
            payroll_run = PayrollRun(
                name=name,
                payroll_year=payroll_year,
                payroll_month=payroll_month,
                status='draft',
                total_employees=len(selected_employees)
            )
            payroll_run.save()
            
            # Store selected employees in session for processing
            request.session[f'payroll_run_{payroll_run.id}_employees'] = selected_employees
            messages.success(request, f'Payroll run "{name}" created with {len(selected_employees)} employees!')
            return redirect('payroll_runs')
            
        except Exception as e:
            messages.error(request, f'Error creating payroll run: {str(e)}')
    
    # GET request - show form with available employees
    current_year = date.today().year
    current_month = date.today().month
    
    # Get selected month/year from request parameters
    selected_year = request.GET.get('year')
    selected_month = request.GET.get('month')
    
    # Use provided values or current values
    try:
        if selected_year:
            selected_year = int(selected_year)
        else:
            selected_year = current_year
            
        if selected_month:
            selected_month = int(selected_month)
        else:
            selected_month = current_month
    except ValueError:
        selected_year = current_year
        selected_month = current_month



    month_start = date(selected_year, selected_month, 1)
    month_end = date(
        selected_year,
        selected_month,
        calendar.monthrange(selected_year, selected_month)[1]
    )

    employees_with_salary = Employee.objects.filter(
        status='active',
        employeesalary__is_active=True,
        employeesalary__effective_date__gte=month_start,
        employeesalary__effective_date__lte=month_end
    ).distinct()

    processed_employee_ids = Payslip.objects.filter(
        payroll_run__payroll_year=selected_year,
        payroll_run__payroll_month=selected_month
    ).values_list('employee_id', flat=True)

    available_employees = employees_with_salary.exclude(
        id__in=processed_employee_ids
    )

    
    # Prepare month list
    months = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
    ]
    
    # Generate years list (current year, previous year, next year)
    years = [current_year - 1, current_year, current_year + 1]
    
    context = {
        'current_year': current_year,
        'current_month': current_month,
        'selected_year': selected_year,
        'selected_month': selected_month,
        'years': years,
        'months': months,
        'available_employees': available_employees,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'payroll/create_payroll_run.html', context)

def process_payroll_run(request, run_id):
    """Process a payroll run and generate payslips for selected employees"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    payroll_run = get_object_or_404(PayrollRun, id=run_id)
    
    if payroll_run.status != 'draft':
        messages.error(request, 'Only draft payroll runs can be processed.')
        return redirect('view_payroll_run', run_id=run_id)
    
    try:
        # Update status to processing
        payroll_run.status = 'processing'
        payroll_run.processed_by = request.session.get('user_name')
        payroll_run.processed_at = timezone.now()
        payroll_run.save()
        
        # Get selected employees from session
        selected_employee_ids = request.session.get(f'payroll_run_{run_id}_employees', [])
        
        if not selected_employee_ids:
            messages.error(request, 'No employees selected for this payroll run.')
            payroll_run.status = 'draft'
            payroll_run.save()
            return redirect('view_payroll_run', run_id=run_id)
        
        total_amount = Decimal('0.00')
        payslips_created = 0
        
        for employee_id in selected_employee_ids:
            try:
                employee = Employee.objects.get(id=employee_id)
                
                # Get active salary for employee
                salary = EmployeeSalary.objects.filter(
                    employee=employee, 
                    is_active=True
                ).first()
                
                if not salary:
                    continue
                
                # Generate payslip number
                payslip_number = f"PS{payroll_run.payroll_year}{payroll_run.payroll_month:02d}{employee.employee_id}_{payroll_run.id}"
                
                # Check if payslip already exists (double check)
                if Payslip.objects.filter(payslip_number=payslip_number).exists():
                    continue
                
                # Calculate attendance stats
                stats = get_attendance_stats(employee, payroll_run.payroll_year, payroll_run.payroll_month)
                working_days = stats['total_days']
                paid_days = stats['paid_days']
                leave_days = stats['absent_days']
                
                # Fetch components to calculate accurate totals
                salary_components = EmployeeSalaryComponent.objects.filter(employee_salary=salary).select_related('component')
                
                total_earnings = Decimal('0.00')
                total_deductions = Decimal('0.00')
                
                for comp in salary_components:
                    if comp.component.component_type == 'earning':
                        total_earnings += comp.amount
                    else:
                        total_deductions += comp.amount
                
                # Accurate Gross and Net
                gross_earnings = salary.basic_salary + total_earnings
                net_salary = gross_earnings - total_deductions

                # Create payslip
                payslip = Payslip(
                    payroll_run=payroll_run,
                    employee=employee,
                    payslip_number=payslip_number,
                    basic_salary=salary.basic_salary,
                    gross_earnings=gross_earnings,
                    total_deductions=total_deductions,
                    net_salary=net_salary,
                    working_days=working_days,
                    paid_days=paid_days,
                    leave_days=leave_days,
                    status='generated'
                )
                payslip.save()
                
                # Create payslip components
                for comp in salary_components:
                    PayslipComponent.objects.create(
                        payslip=payslip,
                        component=comp.component,
                        component_type=comp.component.component_type,
                        amount=comp.amount
                    )
                
                total_amount += net_salary
                payslips_created += 1
                
            except Exception as e:
                print(f"Error processing employee {employee_id}: {str(e)}")
                continue
        
        # Update payroll run totals
        payroll_run.total_employees = payslips_created
        payroll_run.total_amount = total_amount
        payroll_run.status = 'completed'
        payroll_run.save()
        
        # Clear session data
        if f'payroll_run_{run_id}_employees' in request.session:
            del request.session[f'payroll_run_{run_id}_employees']
        
        messages.success(request, f'Payroll run processed successfully! Generated {payslips_created} payslips.')
        
    except Exception as e:
        payroll_run.status = 'draft'
        payroll_run.save()
        messages.error(request, f'Error processing payroll run: {str(e)}')
    
    return redirect('view_payroll_run', run_id=run_id)

def view_payroll_run(request, run_id):
    """View payroll run details"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    payroll_run = get_object_or_404(
        PayrollRun.objects.prefetch_related('payslip_set__employee'),
        id=run_id
    )
    
    payslips = payroll_run.payslip_set.all().select_related('employee')
    
    # Get selected employees from session (for draft runs)
    selected_employee_ids = request.session.get(f'payroll_run_{run_id}_employees', [])
    selected_employees = Employee.objects.filter(id__in=selected_employee_ids) if selected_employee_ids else None
    
    context = {
        'payroll_run': payroll_run,
        'payslips': payslips,
        'selected_employees': selected_employees,
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'payroll/view_payroll_run.html', context)

def delete_payroll_run(request, run_id):
    """Delete a payroll run"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    payroll_run = get_object_or_404(PayrollRun, id=run_id)
    
    if request.method == 'POST':
        # Clear session data
        if f'payroll_run_{run_id}_employees' in request.session:
            del request.session[f'payroll_run_{run_id}_employees']
        
        run_name = payroll_run.name
        payroll_run.delete()
        messages.success(request, f'Payroll run "{run_name}" deleted successfully!')
    
    return redirect('payroll_runs')

from datetime import datetime
from django.db.models import Sum
from django.shortcuts import render, redirect
from .models import Payslip, Employee
from datetime import date

def payslips(request):
    """List all payslips"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
    total_employees = Employee.objects.count()
    # Get current year and month for default filter
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    # Filter payslips based on user role
    if user_role not in ['SUPER ADMIN','ACCOUNTS']:
        try:
            employee = Employee.objects.get(email=user_email)
            payslips_list = Payslip.objects.filter(employee=employee).select_related('payroll_run').order_by('-generated_at')
            # Get total salary for the employee
            total_salary = payslips_list.aggregate(total=Sum('net_salary'))['total'] or 0
        except Employee.DoesNotExist:
            payslips_list = Payslip.objects.none()
            total_salary = 0
    else:
        payslips_list = Payslip.objects.select_related('employee', 'payroll_run').order_by('-generated_at')
        # Get total salary sum for all employees
        total_salary = payslips_list.aggregate(total=Sum('net_salary'))['total'] or 0
    
    # Get pending count for stats
    if user_role not in ['SUPER ADMIN','ACCOUNTS']:
        pending_count = 0  # Employees don't see pending counts
    else:
        success_count = payslips_list.filter(status='generated').count()
        pending_count = total_employees -success_count
    
    context = {
        'total_employees': total_employees,
        'payslips': payslips_list,
        'total_salary_sum': total_salary,
        'pending_count': pending_count,
        'current_year': current_year,
        'current_month': current_month,
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
        'today_date': date.today(),
    }
    
    return render(request, 'payroll/payslips.html', context)
# updated 
def view_payslip(request, payslip_id):
    """View payslip details"""
    if not request.session.get('user_authenticated'):
        return redirect('login')
    
    payslip = get_object_or_404(
        Payslip.objects.select_related('employee', 'payroll_run'),
        id=payslip_id
    )
    
    # Check permission
    user_role = request.session.get('user_role')
    user_email = request.session.get('user_email')
    
    if user_role == 'EMPLOYEE' and payslip.employee.email != user_email:
        messages.error(request, 'You can only view your own payslips.')
        return redirect('access_denied')
    
    components = PayslipComponent.objects.filter(payslip=payslip).select_related('component')
    
    # Calculate dynamic totals for display
    total_earnings = payslip.basic_salary
    total_deductions = Decimal('0.00')
    
    for comp in components:
        if comp.component_type == 'earning':
            total_earnings += comp.amount
        else:
            total_deductions += comp.amount
            
    # Fetch live attendance stats
    attendance_stats = get_attendance_stats(
        payslip.employee, 
        payslip.payroll_run.payroll_year, 
        payslip.payroll_run.payroll_month
    )
    
    context = {
        'payslip': payslip,
        'components': components,
        'total_earnings': total_earnings,
        'total_deductions': total_deductions,
        'net_salary': total_earnings - total_deductions,
        'attendance_stats': attendance_stats,
        'user_name': request.session.get('user_name'),
        'user_role': user_role,
        'today_date': date.today(),
    }
    
    return render(request, 'payroll/view_payslip.html', context)

# download 
def generate_payslip_pdf(payslip):
    """Generate PDF for payslip"""
    buffer = io.BytesIO()
    
    # Create PDF document
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=1,  # Center alignment
    )
    
    # Title
    title = Paragraph("PAYSLIP", title_style)
    elements.append(title)
    
    # Company and Employee Info
    company_info = [
        ["Company: HR Management System", f"Payslip No: {payslip.payslip_number}"],
        ["Address: Your Company Address", f"Payment Date: {payslip.generated_at.strftime('%d-%m-%Y')}"],
        ["Phone: +1234567890", f"Payment Month: {payslip.payroll_run.payroll_month}/{payslip.payroll_run.payroll_year}"]
    ]
    
    company_table = Table(company_info, colWidths=[3*inch, 3*inch])
    company_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(company_table)
    elements.append(Spacer(1, 20))
    
    # Employee Details
    employee_info = [
        ["EMPLOYEE DETAILS", ""],
        ["Employee Name:", f"{payslip.employee.first_name} {payslip.employee.last_name}"],
        ["Employee ID:", payslip.employee.employee_id],
        ["Department:", payslip.employee.department],
        ["Designation:", payslip.employee.designation],
        ["Bank Account:", f"****{payslip.employee.account_number[-4:]}" if payslip.employee.account_number else "N/A"],
    ]
    
    employee_table = Table(employee_info, colWidths=[2*inch, 4*inch])
    employee_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 12),
    ]))
    elements.append(employee_table)
    elements.append(Spacer(1, 20))
    
    # Salary Breakdown
    # Get payslip components
    components = PayslipComponent.objects.filter(payslip=payslip)
    
    # Earnings
    earnings_data = [["EARNINGS", "AMOUNT (₹)"]]
    earnings_data.append(["Basic Salary", f"{payslip.basic_salary:.2f}"])
    total_earnings = payslip.basic_salary
    
    for component in components.filter(component_type='earning'):
        earnings_data.append([component.component.name, f"{component.amount:.2f}"])
        total_earnings += component.amount
    
    earnings_data.append(["Total Earnings", f"{total_earnings:.2f}"])
    
    earnings_table = Table(earnings_data, colWidths=[4*inch, 2*inch])
    earnings_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('BACKGROUND', (0, 1), (-1, -2), colors.white),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 12),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
    ]))
    elements.append(earnings_table)
    elements.append(Spacer(1, 15))
    
    # Deductions
    deductions_data = [["DEDUCTIONS", "AMOUNT (₹)"]]
    total_deductions = 0
    
    for component in components.filter(component_type='deduction'):
        deductions_data.append([component.component.name, f"{component.amount:.2f}"])
        total_deductions += component.amount
    
    deductions_data.append(["Total Deductions", f"{total_deductions:.2f}"])
    
    deductions_table = Table(deductions_data, colWidths=[4*inch, 2*inch])
    deductions_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightcoral),
        ('BACKGROUND', (0, 1), (-1, -2), colors.white),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 12),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
    ]))
    elements.append(deductions_table)
    elements.append(Spacer(1, 20))
    
    # Summary
    summary_data = [
        ["SUMMARY", "AMOUNT (₹)"],
        ["Basic Salary:", f"{payslip.basic_salary:.2f}"],
        ["Gross Earnings:", f"{total_earnings:.2f}"],
        ["Total Deductions:", f"{total_deductions:.2f}"],
        ["NET SALARY:", f"{(total_earnings - total_deductions):.2f}"],
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 3*inch])
    summary_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 11),
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (-1, -2), colors.white),
        ('BACKGROUND', (0, -1), (-1, -1), colors.green),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 12),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 12),
    ]))
    elements.append(summary_table)
    
    # Attendance Summary
    elements.append(Spacer(1, 20))
    stats = get_attendance_stats(payslip.employee, payslip.payroll_run.payroll_year, payslip.payroll_run.payroll_month)
    attendance_data = [
        ["ATTENDANCE SUMMARY", ""],
        ["Total Days:", str(stats['total_days'])],
        ["Paid Days:", str(stats['paid_days'])],
        ["LOP Days:", str(stats['absent_days'])],
    ]
    
    attendance_table = Table(attendance_data, colWidths=[3*inch, 3*inch])
    attendance_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 12),
    ]))
    elements.append(attendance_table)
    
    # Footer
    elements.append(Spacer(1, 30))
    footer = Paragraph(
        "This is a computer-generated payslip and does not require a signature.",
        styles['Normal']
    )
    elements.append(footer)
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF value from buffer
    pdf = buffer.getvalue()
    buffer.close()
    
    return pdf



def number_to_words(number):
    """Convert number to words (basic implementation)"""
    try:
        num = float(number)
        if num == 0:
            return "Zero rupees only"
        
        # Basic implementation - you can enhance this
        units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
        teens = ["Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
        
        def convert_below_100(n):
            if n < 10:
                return units[n]
            elif n < 20:
                return teens[n-10]
            else:
                return tens[n//10] + (" " + units[n%10] if n%10 != 0 else "")
        
        def convert_below_1000(n):
            if n < 100:
                return convert_below_100(n)
            else:
                return units[n//100] + " Hundred" + (" " + convert_below_100(n%100) if n%100 != 0 else "")
        
        # For simplicity, handling up to 99,999
        if num <= 99999:
            if num < 1000:
                words = convert_below_1000(int(num))
            else:
                words = convert_below_1000(int(num)//1000) + " Thousand"
                if num % 1000 != 0:
                    words += " " + convert_below_1000(int(num)%1000)
            
            return words + " rupees only"
        else:
            return f"{num:,.2f} rupees only"
            
    except:
        return f"{number} rupees only"


class PayslipPDF(FPDF):
    def __init__(self, month_name="", year=""):
        super().__init__()
        self.month_name = month_name
        self.year = year
        # ✅ Use Unicode-supported DejaVuSans font
        font_path = os.path.join(settings.BASE_DIR, "static", "fonts", "DejaVuSans.ttf")
        self.add_font("DejaVu", "", font_path, uni=True)
        self.add_font("DejaVu", "B", font_path, uni=True)
        self.add_font("DejaVu", "I", font_path, uni=True)
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        # ✅ Company Logo + Header
        logo_path = os.path.join(settings.BASE_DIR, "static", "img", "logosoftmate.jpeg")
        try:
            self.image(logo_path, 155, 12, 45)
        except:
            pass

        self.set_font("DejaVu", "B", 16)
        self.cell(
            0,
            10,
            f"PAYSLIP - {self.month_name.upper()} {self.year}",
            ln=True,
            align="L",
        )

        self.set_font("DejaVu", "", 9)
        self.multi_cell(
            0,
            5,
            "\nIKONTEL SOLUTIONS PVT LTD\n\n"
            "NO.72, 73 & 74, 1ST FLOOR AMRBP BUILDING, MARGOSA ROAD, 17TH CROSS RD,"
            "\nMALLESWARAM"
            "\nBENGALURU, KARNATAKA | IKONTEL SOLUTIONS PVT LTD",
            align="L",
        )
        # self.ln(3)
        # self.set_draw_color(0, 0, 0)
        # self.set_line_width(0.4)
        # self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def section_box(self, title):
        self.set_font("DejaVu", "B", 11)
        self.set_fill_color(240, 240, 240)
        self.cell(0, 8, f" {title}", ln=True, fill=True)
        self.ln(2)

    def cell_pair(self, label, value, w=45):
        """Label-value pair (no borders)"""
        self.set_font("DejaVu", "", 9)
        self.cell(w, 7, f"{label}:", align="L")
        self.cell(w + 25, 7, f"{value}", align="L")

    def salary_table(self, title, data, total_label, payslip=None):
        """
        Salary components (no borders)
        - For EARNINGS: includes Basic Salary (from payslip.basic_salary) + earning components
        - For DEDUCTIONS: includes only deduction components
        """
        self.section_box(title)
        self.set_font("DejaVu", "B", 9)
        self.cell(100, 8, "Component", align="L")
        self.cell(50, 8, "Amount (₹)", align="R", ln=True)

        self.set_font("DejaVu", "", 9)

        total = 0.0

        # Show Basic Salary only in EARNINGS table
        if (
            payslip
            and hasattr(payslip, "basic_salary")
            and title.strip().upper() == "EARNINGS"
        ):
            basic_salary = float(payslip.basic_salary or 0)
            self.cell(100, 7, "Basic Salary", align="L")
            self.cell(50, 7, f"{basic_salary:,.2f}", align="R", ln=True)
            total += basic_salary

        # Show all components
        for comp in data:
            comp_name = comp.component.name
            comp_amount = float(comp.amount or 0)
            self.cell(100, 7, comp_name, align="L")
            self.cell(50, 7, f"{comp_amount:,.2f}", align="R", ln=True)
            total += comp_amount

        # Total row
        self.set_font("DejaVu", "B", 9)
        self.cell(100, 8, total_label, align="L")
        self.cell(50, 8, f"{total:,.2f}", align="R", ln=True)
        self.ln(4)
        
        
def download_payslip(request, payslip_id):
    try:
        # Fetch Payslip Data
        payslip = Payslip.objects.select_related("employee", "payroll_run").get(
            id=payslip_id
        )
        all_components = PayslipComponent.objects.filter(
            payslip=payslip
        ).select_related("component")

        earnings = all_components.filter(component_type="earning")
        deductions = all_components.filter(component_type="deduction")

        # If you still want totals in Python (for logging/debug, not used in PDF now)
        total_earn = sum(float(c.amount) for c in earnings)
        total_deduct = sum(float(c.amount) for c in deductions)
        
        # ---- Month & Year (SINGLE SOURCE) ----
        if payslip.payroll_run and payslip.payroll_run.payroll_month:
            month_name = datetime(
                1900, int(payslip.payroll_run.payroll_month), 1
            ).strftime("%B")
        else:
            month_name = "Month"

        year = (
            payslip.payroll_run.payroll_year
            if payslip.payroll_run and payslip.payroll_run.payroll_year
            else "Year"
        )

        # ---- PDF ----
        pdf = PayslipPDF(month_name=month_name, year=year)
        pdf.add_page()

        # Employee Info
        pdf.set_font("DejaVu", "B", 10)
        pdf.cell(
            0,
            7,
            f"{payslip.employee.first_name} {payslip.employee.last_name}",
            ln=True,
        )

        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.4)
        pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
        pdf.ln(5)

        pdf.set_font("DejaVu", "", 9)

        def add_row(labels_values):
            col_width = 47
            for label, value in labels_values:
                pdf.set_font("DejaVu", "B", 9)
                pdf.cell(col_width, 6, label, border=0)
            pdf.ln(5)
            for label, value in labels_values:
                pdf.set_font("DejaVu", "", 9)
                pdf.cell(col_width, 6, str(value), border=0)
            pdf.ln(8)

        add_row(
            [
                ("Employee Code", payslip.employee.employee_id),
                (
                    "Date Joined",
                    payslip.employee.date_of_joining.strftime("%d %b %Y"),
                ),
                ("Department", payslip.employee.department or "N/A"),
                ("Designation", payslip.employee.designation or "N/A"),
            ]
        )

        add_row(
            [
                ("Bank", payslip.employee.bank_name or "N/A"),
                ("Bank Account", payslip.employee.account_number or "N/A"),
                ("Bank IFSC", payslip.employee.ifsc_code or "N/A"),
                ("Payment Mode", "Bank Transfer"),
            ]
        )

        add_row(
            [
                ("UAN", payslip.employee.uan if hasattr(payslip.employee, "uan") else "N/A"),
                ("PF Number", payslip.employee.pf_number if hasattr(payslip.employee, "pf_number") else "N/A"),
                ("ESI Number", payslip.employee.esi_number if hasattr(payslip.employee, "esi_number") else "N/A"),
                ("", ""),
            ]
        )

        pdf.ln(3)

        # Salary Details
        pdf.cell(0, 7, "Salary Details", ln=True)

        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.4)
        pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
        pdf.ln(5)

        pdf.set_font("DejaVu", "B", 9)
        pdf.cell(47.5, 6, "Total Working Days", border=0)
        pdf.cell(47.5, 6, "Paid Days", border=0)
        pdf.cell(47.5, 6, "Loss of Pay", border=0)
        pdf.cell(47.5, 6, "Total Payable Days", border=0)
        pdf.ln(6)

        pdf.set_font("DejaVu", "", 9)
        pdf.cell(47.5, 6, str(payslip.working_days), border=0)
        pdf.cell(47.5, 6, str(payslip.paid_days), border=0)
        pdf.cell(47.5, 6, str(payslip.leave_days), border=0)
        pdf.cell(47.5, 6, str(payslip.paid_days - payslip.leave_days), border=0)
        pdf.ln(10)

        # Tables (FIXED: totals are not doubled now)
        pdf.salary_table("EARNINGS", earnings, "Total Earnings (A)", payslip=payslip)
        pdf.salary_table("DEDUCTIONS", deductions, "Total Deductions (B)")

        # Summary
        net_salary = payslip.net_salary
        net_words = number_to_words(net_salary)
        pdf.section_box("SUMMARY")
        pdf.cell(100, 8, "Net Salary Payable (A - B)", align="L")
        pdf.cell(50, 8, f"₹{net_salary:.2f}", align="R", ln=True)
        pdf.ln(4)
        pdf.multi_cell(0, 7, f"Net Salary (in words): {net_words}", align="L")
        pdf.ln(5)
        pdf.set_font("DejaVu", "I", 8)
        pdf.multi_cell(
            0, 6, "*Note: All amounts displayed in this payslip are in INR."
        )

        pdf_buffer = io.BytesIO()
        pdf.output(pdf_buffer)
        pdf_buffer.seek(0)

        response = HttpResponse(pdf_buffer, content_type="application/pdf")

        if payslip.payroll_run and payslip.payroll_run.payroll_month:
            month_number = int(payslip.payroll_run.payroll_month)
            month_name = datetime(1900, month_number, 1).strftime("%B")
        else:
            month_name = "Month"

        year_value = (
            payslip.payroll_run.payroll_year
            if payslip.payroll_run and payslip.payroll_run.payroll_year
            else "Year"
        )

        employee_name = (
            f"{payslip.employee.first_name}_{payslip.employee.last_name}".replace(
                " ", "_"
            )
        )
        filename = f"Payslip_{employee_name}_{month_name}_{year_value}.pdf"

        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response

    except Payslip.DoesNotExist:
        return HttpResponse("Payslip not found.")
    except Exception as e:
        return HttpResponse(f"Error generating PDF: {e}")


def view_employee_salary(request, salary_id):
    salary = get_object_or_404(EmployeeSalary, id=salary_id)
    components = EmployeeSalaryComponent.objects.filter(
        employee_salary=salary
    ).select_related("component")

    total_earnings = salary.basic_salary
    total_deductions = Decimal("0.00")
    
    for comp in components:
        if comp.component.component_type == "earning":
            total_earnings += comp.amount
        else:
            total_deductions += comp.amount

    context = {
        "salary": salary,
        "components": components,
        "total_earnings": total_earnings,
        "total_deductions": total_deductions,
        "user_name": request.session.get("user_name"),
        "user_role": request.session.get("user_role"),
        "today_date": date.today(),
    }
    return render(request, "payroll/view_employee_salary.html", context)

def edit_employee_salary(request, salary_id):
    salary = get_object_or_404(EmployeeSalary, id=salary_id)
    components = SalaryComponent.objects.filter(is_active=True)
    existing_components = EmployeeSalaryComponent.objects.filter(employee_salary=salary)
    
    if request.method == 'POST':
        try:
            salary.effective_date = request.POST.get('effective_date')
            salary.basic_salary = Decimal(request.POST.get('basic_salary', 0))
            salary.save()
            
            # Update components
            for component in components:
                amount_key = f'component_{component.id}'
                amount = request.POST.get(amount_key, 0) or 0
                
                existing_component = existing_components.filter(component=component).first()
                if existing_component:
                    if Decimal(amount) > 0:
                        existing_component.amount = Decimal(amount)
                        existing_component.save()
                    else:
                        existing_component.delete()
                elif Decimal(amount) > 0:
                    EmployeeSalaryComponent(
                        employee_salary=salary,
                        component=component,
                        amount=Decimal(amount),
                        updated_by=request.session.get('user_name')
                    ).save()
            
            # Recalculate totals
            salary = calculate_salary_totals(salary)
            
            messages.success(request, 'Salary structure updated successfully!')
            return redirect('employee_salaries')
            
        except Exception as e:
            messages.error(request, f'Error updating salary structure: {str(e)}')
    
    context = {
        'salary': salary,
        'components': components,
        'existing_components': {ec.component.id: ec.amount for ec in existing_components},
        'user_name': request.session.get('user_name'),
        'user_role': request.session.get('user_role'),
        'today_date': date.today(),
    }
    return render(request, 'payroll/edit_employee_salary.html', context)

def calculate_true_lop_days(employee, year, month):
    """
    Compute the TRUE Loss of Pay (LOP) days for an employee in a given month.

    FORMULA:
        True LOP = Attendance Deductions - Approved Paid Leave Coverage

    Attendance Deductions:
        - Absent (no check-in, no leave applied)  → 1.0 day
        - LOP (worked < 2 hrs)                    → 1.0 day
        - Half Day (worked 2-5 hrs, Mon-Fri)       → 0.5 day
        - Half Day on Saturday                     → 0.0 (counts as Present)
        - Present / Sunday / Holiday               → 0.0

    Approved Paid Leave Coverage (reduces deduction):
        - Full-day approved paid leave             → -1.0
        - Half-day approved paid leave             → -0.5
        (Unpaid leave does NOT reduce the deduction)
    """
    from calendar import monthrange
    from datetime import date, timedelta

    today = date.today()
    start_date = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    end_date = date(year, month, last_day)
    # Don't count future dates
    if end_date > today:
        end_date = today

    all_dates = [
        start_date + timedelta(days=i)
        for i in range((end_date - start_date).days + 1)
    ]

    # ── Step 1: Build attendance lookup ───────────────────────────────────────
    attendances = Attendance.objects.filter(
        employee=employee,
        date__range=[start_date, end_date]
    )
    att_dict = {a.date: a for a in attendances}

    # ── Step 2: Build holiday set for the employee's location ─────────────────
    holiday_dates = set(
        Holiday.objects.filter(
            date__range=[start_date, end_date],
            region__name__iexact=employee.location
        ).values_list('date', flat=True)
    )

    print(f"\n{'='*60}")
    print(f"[LOP] {employee.first_name} {employee.last_name} | {year}-{month:02d}")
    print(f"[LOP] Scanning: {start_date} to {end_date}")
    print(f"[LOP] Attendance records: {len(att_dict)} | Holidays: {sorted(holiday_dates)}")

    # ── Step 3: Compute raw attendance deductions ─────────────────────────────
    total_deduction = 0.0

    for d in all_dates:
        if d.weekday() == 6:
            continue  # Sunday - skip silently
        if d in holiday_dates:
            print(f"  [{d}] Holiday → skip")
            continue

        att = att_dict.get(d)

        if att and att.check_in and att.check_out:
            diff = att.check_out - att.check_in
            worked_hours = diff.total_seconds() / 3600

            if worked_hours < 2:
                total_deduction += 1.0
                print(f"  [{d}] LOP ({worked_hours:.2f}h worked) → +1.0")
            elif worked_hours < 5:
                if d.weekday() == 5:
                    print(f"  [{d}] Half Day Saturday ({worked_hours:.2f}h) → 0 (Present)")
                else:
                    total_deduction += 0.5
                    print(f"  [{d}] Half Day ({worked_hours:.2f}h) → +0.5")
            else:
                pass  # Present → no deduction

        elif att and att.check_in and not att.check_out:
            if d.weekday() != 5:
                total_deduction += 0.5
                print(f"  [{d}] Check-in only (no checkout) → +0.5")
        else:
            total_deduction += 1.0
            print(f"  [{d}] Absent (no record) → +1.0")

    print(f"[LOP] Raw deduction total: {total_deduction}")

    # ── Step 4: Subtract approved PAID leave coverage ─────────────────────────
    approved_paid_leaves = Leave.objects.filter(
        employee=employee,
        status='approved',
        start_date__lte=end_date,
        end_date__gte=start_date,
        is_unpaid=False,
    ).exclude(
        leave_type__name__icontains='unpaid'
    )

    print(f"[LOP] Approved paid leaves found: {approved_paid_leaves.count()}")
    paid_leave_coverage = 0.0

    for leave in approved_paid_leaves:
        leave_start = max(leave.start_date, start_date)
        leave_end   = min(leave.end_date,   end_date)

        if leave.is_half_day:
            d = leave.start_date
            if start_date <= d <= end_date:
                if d.weekday() != 6 and d not in holiday_dates:
                    paid_leave_coverage += 0.5
                    print(f"  [LEAVE] Half-day on {d} ({leave.leave_type.name}) → covers 0.5")
        else:
            # Prorate days_requested over working days in range to handle partial days correctly
            total_working = float(leave.get_working_days())
            daily_val = float(leave.days_requested) / total_working if total_working > 0 else 0
            
            cur = leave_start
            while cur <= leave_end:
                if cur.weekday() != 6 and cur not in holiday_dates:
                    paid_leave_coverage += daily_val
                    print(f"  [LEAVE] Day on {cur} ({leave.leave_type.name}) -> covers {daily_val:.2f}")
                cur += timedelta(days=1)

    print(f"[LOP] Paid leave coverage: {paid_leave_coverage}")

    # ── Step 5: True LOP ──────────────────────────────────────────────────────
    true_lop = max(0.0, total_deduction - paid_leave_coverage)
    print(f"[LOP] RESULT: {total_deduction} - {paid_leave_coverage} = {true_lop}")
    print(f"{'='*60}\n")
    return round(true_lop, 2)


def get_employee_salary_data(request, employee_id):
    """API endpoint to get employee salary and LOP data for payroll calculator"""
    try:
        employee = Employee.objects.get(id=employee_id)
        # # Get unpaid leave balance
        # unpaid_leave_balance = LeaveBalance.objects.filter(
        #     employee_id=employee_id, 
        #     leave_type__name='unpaid'
        # ).first()

        # ── Read month/year from query params (e.g. ?month=4&year=2026) ────────
        today = date.today()
        try:
            month = int(request.GET.get('month', today.month))
            year  = int(request.GET.get('year',  today.year))
        except (ValueError, TypeError):
            month, year = today.month, today.year

        # ── Compute True LOP from attendance + leave ───────────────────────────
        lop_days = calculate_true_lop_days(employee, year, month)

        data = {
            'basic_salary': float(employee.basic_salary) if employee.basic_salary else 0,
            # 'unpaid_leave_balance': float(unpaid_leave_balance.leaves_taken) if unpaid_leave_balance else 0,
            'unpaid_leave_balance': lop_days,   # True LOP days for salary deduction
            'month': month,
            'year': year,
        }
        return JsonResponse(data)

    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Employee not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
