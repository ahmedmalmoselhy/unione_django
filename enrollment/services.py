from datetime import datetime, time, timedelta, timezone

from .models import CourseEnrollment


GRADE_POINTS_MAP = {
	'A+': 4.0,
	'A': 4.0,
	'A-': 3.7,
	'B+': 3.3,
	'B': 3.0,
	'B-': 2.7,
	'C+': 2.3,
	'C': 2.0,
	'C-': 1.7,
	'D+': 1.3,
	'D': 1.0,
	'F': 0.0,
}


def _safe_grade_points(letter_grade, numeric_points):
	if letter_grade:
		points = GRADE_POINTS_MAP.get(str(letter_grade).upper())
		if points is not None:
			return points

	if numeric_points is None:
		return None

	try:
		value = float(numeric_points)
	except (TypeError, ValueError):
		return None

	# Fallback mapping from 0-100 to 0-4 grade points.
	return max(0.0, min(4.0, value / 25.0))


def build_student_transcript(student_profile, academic_term_id=None):
	queryset = (
		CourseEnrollment.objects.select_related(
			'academic_term',
			'section__course',
			'grade',
		)
		.filter(student=student_profile)
		.exclude(status=CourseEnrollment.EnrollmentStatus.DROPPED)
		.order_by('academic_term__start_date', 'section__course__code', 'id')
	)

	if academic_term_id:
		queryset = queryset.filter(academic_term_id=academic_term_id)

	terms = []
	term_index = {}
	cumulative_attempted_credits = 0
	cumulative_earned_credits = 0
	cumulative_quality_points = 0.0
	cumulative_gpa_credits = 0

	for enrollment in queryset:
		term = enrollment.academic_term
		course = enrollment.section.course
		grade = getattr(enrollment, 'grade', None)
		credit_hours = int(course.credit_hours or 0)
		grade_points = _safe_grade_points(
			getattr(grade, 'letter_grade', None),
			getattr(grade, 'points', None),
		)

		if term.id not in term_index:
			term_payload = {
				'id': term.id,
				'name': term.name,
				'start_date': term.start_date,
				'end_date': term.end_date,
				'courses': [],
				'statistics': {
					'attempted_credit_hours': 0,
					'earned_credit_hours': 0,
					'term_gpa': None,
				},
				'_quality_points': 0.0,
				'_gpa_credits': 0,
			}
			term_index[term.id] = term_payload
			terms.append(term_payload)

		current_term = term_index[term.id]
		current_term['courses'].append(
			{
				'enrollment_id': enrollment.id,
				'course': {
					'id': course.id,
					'code': course.code,
					'name': course.name,
					'credit_hours': credit_hours,
				},
				'status': enrollment.status,
				'grade': {
					'points': getattr(grade, 'points', None),
					'letter_grade': getattr(grade, 'letter_grade', None),
					'status': getattr(grade, 'status', None),
					'grade_points': grade_points,
				},
			}
		)

		current_term['statistics']['attempted_credit_hours'] += credit_hours
		cumulative_attempted_credits += credit_hours

		if grade is not None and grade.status == 'complete' and grade_points is not None:
			quality_points = grade_points * credit_hours
			current_term['_quality_points'] += quality_points
			current_term['_gpa_credits'] += credit_hours
			cumulative_quality_points += quality_points
			cumulative_gpa_credits += credit_hours

			if grade_points > 0.0:
				current_term['statistics']['earned_credit_hours'] += credit_hours
				cumulative_earned_credits += credit_hours

	for term_payload in terms:
		if term_payload['_gpa_credits'] > 0:
			term_payload['statistics']['term_gpa'] = round(
				term_payload['_quality_points'] / term_payload['_gpa_credits'],
				2,
			)
		del term_payload['_quality_points']
		del term_payload['_gpa_credits']

	transcript = {
		'student': {
			'id': student_profile.id,
			'student_number': student_profile.student_number,
			'faculty': student_profile.faculty.name,
			'department': student_profile.department.name,
			'academic_year': student_profile.academic_year,
			'semester': student_profile.semester,
		},
		'terms': terms,
		'summary': {
			'attempted_credit_hours': cumulative_attempted_credits,
			'earned_credit_hours': cumulative_earned_credits,
			'cumulative_gpa': round(cumulative_quality_points / cumulative_gpa_credits, 2)
			if cumulative_gpa_credits > 0
			else None,
		},
	}

	return transcript


def build_student_academic_history(student_profile):
	transcript = build_student_transcript(student_profile)
	records = []

	for term in transcript['terms']:
		for course_item in term['courses']:
			records.append(
				{
					'academic_term': {
						'id': term['id'],
						'name': term['name'],
						'start_date': term['start_date'],
						'end_date': term['end_date'],
					},
					'course': course_item['course'],
					'enrollment_status': course_item['status'],
					'grade': course_item['grade'],
				}
			)

	return {
		'student': transcript['student'],
		'records': records,
		'summary': transcript['summary'],
	}


def build_student_schedule(student_profile, academic_term_id=None):
	queryset = (
		CourseEnrollment.objects.select_related(
			'section__course',
			'section__professor__user',
			'section__academic_term',
		)
		.filter(student=student_profile)
		.exclude(status=CourseEnrollment.EnrollmentStatus.DROPPED)
		.order_by('section__academic_term__start_date', 'section__id')
	)

	if academic_term_id:
		queryset = queryset.filter(academic_term_id=academic_term_id)

	data = []
	for enrollment in queryset:
		section = enrollment.section
		course = section.course
		term = section.academic_term
		professor = section.professor

		data.append(
			{
				'enrollment_id': enrollment.id,
				'status': enrollment.status,
				'academic_term': {
					'id': term.id,
					'name': term.name,
					'start_date': term.start_date,
					'end_date': term.end_date,
				},
				'section': {
					'id': section.id,
					'semester': section.semester,
					'capacity': section.capacity,
					'schedule': section.schedule,
					'course': {
						'id': course.id,
						'code': course.code,
						'name': course.name,
						'credit_hours': course.credit_hours,
					},
					'professor': {
						'id': professor.id,
						'name': professor.user.get_full_name() or professor.user.username,
						'staff_number': professor.staff_number,
					},
				},
			}
		)

	return data


def _parse_hhmm(value, default_hour):
	if isinstance(value, str) and ':' in value:
		parts = value.split(':')
		if len(parts) >= 2:
			try:
				hour = int(parts[0])
				minute = int(parts[1])
				if 0 <= hour <= 23 and 0 <= minute <= 59:
					return time(hour=hour, minute=minute)
			except ValueError:
				pass
	return time(hour=default_hour, minute=0)


def _first_date_for_weekday(start_date, weekday):
	delta = (weekday - start_date.weekday()) % 7
	return start_date + timedelta(days=delta)


def _ics_escape(value):
	return str(value).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def build_student_schedule_ics(student_profile, academic_term_id=None):
	queryset = (
		CourseEnrollment.objects.select_related(
			'section__course',
			'section__professor__user',
			'section__academic_term',
		)
		.filter(student=student_profile)
		.exclude(status=CourseEnrollment.EnrollmentStatus.DROPPED)
		.order_by('section__academic_term__start_date', 'section__id')
	)

	if academic_term_id:
		queryset = queryset.filter(academic_term_id=academic_term_id)

	day_map = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
	lines = [
		'BEGIN:VCALENDAR',
		'VERSION:2.0',
		'PRODID:-//UniOne//Django//EN',
		'CALSCALE:GREGORIAN',
		'X-WR-CALNAME:UniOne Student Schedule',
	]
	dtstamp = datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')

	for enrollment in queryset:
		section = enrollment.section
		term = section.academic_term
		schedule = section.schedule or {}
		days = schedule.get('days') if isinstance(schedule, dict) else []
		start_time = _parse_hhmm(schedule.get('start_time') if isinstance(schedule, dict) else None, 9)
		end_time = _parse_hhmm(schedule.get('end_time') if isinstance(schedule, dict) else None, 10)

		if not isinstance(days, list):
			continue

		for raw_day in days:
			try:
				day_value = int(raw_day)
			except (TypeError, ValueError):
				continue

			if 1 <= day_value <= 7:
				weekday = day_value - 1
			elif 0 <= day_value <= 6:
				weekday = day_value
			else:
				continue

			first_date = _first_date_for_weekday(term.start_date, weekday)
			if first_date > term.end_date:
				continue

			dtstart = datetime.combine(first_date, start_time, tzinfo=timezone.utc)
			dtend = datetime.combine(first_date, end_time, tzinfo=timezone.utc)
			until = datetime.combine(term.end_date, time(23, 59, 59), tzinfo=timezone.utc)

			summary = f"{section.course.code} - {section.course.name}"
			description = (
				f"Professor: {(section.professor.user.get_full_name() or section.professor.user.username)}\\n"
				f"Term: {term.name}"
			)
			uid = f"student-{student_profile.id}-section-{section.id}-day-{weekday}@unione.local"

			lines.extend(
				[
					'BEGIN:VEVENT',
					f'UID:{uid}',
					f'DTSTAMP:{dtstamp}',
					f'DTSTART:{dtstart.strftime("%Y%m%dT%H%M%SZ")}',
					f'DTEND:{dtend.strftime("%Y%m%dT%H%M%SZ")}',
					f'RRULE:FREQ=WEEKLY;BYDAY={day_map[weekday]};UNTIL={until.strftime("%Y%m%dT%H%M%SZ")}',
					f'SUMMARY:{_ics_escape(summary)}',
					f'DESCRIPTION:{_ics_escape(description)}',
					'END:VEVENT',
				]
			)

	lines.append('END:VCALENDAR')
	return '\r\n'.join(lines) + '\r\n'


def _pdf_escape(value):
	text = str(value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
	return text.replace('\n', ' ')


def _build_simple_pdf_from_lines(lines):
	if not lines:
		lines = ['UniOne Transcript']

	max_lines_per_page = 46
	chunks = [lines[i : i + max_lines_per_page] for i in range(0, len(lines), max_lines_per_page)]
	page_count = len(chunks)
	font_object_id = 3 + (page_count * 2)

	objects = {
		1: b'<< /Type /Catalog /Pages 2 0 R >>',
		2: (
			f"<< /Type /Pages /Kids [{' '.join(f'{3 + (idx * 2)} 0 R' for idx in range(page_count))}] "
			f"/Count {page_count} >>"
		).encode('ascii'),
	}

	for idx, chunk in enumerate(chunks):
		page_object_id = 3 + (idx * 2)
		content_object_id = 4 + (idx * 2)

		objects[page_object_id] = (
			f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] '
			f'/Resources << /Font << /F1 {font_object_id} 0 R >> >> '
			f'/Contents {content_object_id} 0 R >>'
		).encode('ascii')

		stream_commands = ['BT', '/F1 10 Tf', '50 800 Td']
		for line_number, line in enumerate(chunk):
			stream_commands.append(f'({_pdf_escape(line)}) Tj')
			if line_number < len(chunk) - 1:
				stream_commands.append('0 -14 Td')
		stream_commands.append('ET')

		stream_bytes = '\n'.join(stream_commands).encode('latin-1', 'replace')
		objects[content_object_id] = (
			b'<< /Length '
			+ str(len(stream_bytes)).encode('ascii')
			+ b' >>\nstream\n'
			+ stream_bytes
			+ b'\nendstream'
		)

	objects[font_object_id] = b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'

	max_object_id = max(objects.keys())
	pdf_bytes = bytearray()
	pdf_bytes.extend(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')

	offsets = {0: 0}
	for object_id in range(1, max_object_id + 1):
		offsets[object_id] = len(pdf_bytes)
		pdf_bytes.extend(f'{object_id} 0 obj\n'.encode('ascii'))
		pdf_bytes.extend(objects[object_id])
		pdf_bytes.extend(b'\nendobj\n')

	xref_offset = len(pdf_bytes)
	pdf_bytes.extend(f'xref\n0 {max_object_id + 1}\n'.encode('ascii'))
	pdf_bytes.extend(b'0000000000 65535 f \n')
	for object_id in range(1, max_object_id + 1):
		pdf_bytes.extend(f'{offsets[object_id]:010d} 00000 n \n'.encode('ascii'))

	pdf_bytes.extend(
		f'trailer\n<< /Size {max_object_id + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n'.encode('ascii')
	)
	return bytes(pdf_bytes)


def build_student_transcript_pdf_bytes(student_profile, academic_term_id=None):
	"""Generate professional PDF transcript using ReportLab."""
	from reportlab.lib import colors
	from reportlab.lib.pagesizes import letter
	from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
	from reportlab.lib.units import inch
	from reportlab.platypus import (
		SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, KeepTogether
	)
	
	transcript = build_student_transcript(student_profile, academic_term_id=academic_term_id)
	buffer = io.BytesIO()
	
	doc = SimpleDocTemplate(
		buffer,
		pagesize=letter,
		rightMargin=72,
		leftMargin=72,
		topMargin=72,
		bottomMargin=72,
		title=f"Transcript - {transcript['student']['student_number']}",
		author="UniOne University",
	)
	
	styles = getSampleStyleSheet()
	
	# Custom styles
	title_style = ParagraphStyle(
		'CustomTitle',
		parent=styles['Heading1'],
		fontSize=18,
		spaceAfter=6,
		textColor=colors.HexColor('#1a365d'),
		alignment=1,  # Center
	)
	
	header_style = ParagraphStyle(
		'Header',
		parent=styles['Normal'],
		fontSize=10,
		spaceAfter=4,
	)
	
	section_style = ParagraphStyle(
		'Section',
		parent=styles['Heading2'],
		fontSize=12,
		spaceBefore=12,
		spaceAfter=6,
		textColor=colors.HexColor('#2c5282'),
	)
	
	elements = []
	
	# Title
	elements.append(Paragraph("UniOne University", title_style))
	elements.append(Paragraph("Official Student Transcript", ParagraphStyle('Subtitle', parent=styles['Heading2'], alignment=1, fontSize=14, textColor=colors.HexColor('#2d3748'))))
	elements.append(Spacer(1, 0.3*inch))
	
	# Student info
	student = transcript['student']
	info_data = [
		['Student Number:', student['student_number'], 'Faculty:', student['faculty']],
		['Department:', student['department'], 'Academic Year:', str(student['academic_year'])],
		['Semester:', str(student['semester']), 'Enrollment Status:', student['enrollment_status']],
	]
	info_table = Table(info_data, colWidths=[1.5*inch, 2*inch, 1.5*inch, 2*inch])
	info_table.setStyle(TableStyle([
		('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
		('FONTSIZE', (0, 0), (-1, -1), 9),
		('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#4a5568')),
		('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#4a5568')),
		('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
		('FONTNAME', (3, 0), (3, -1), 'Helvetica-Bold'),
		('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f7fafc')),
		('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#f7fafc')),
		('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
		('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
		('TOPPADDING', (0, 0), (-1, -1), 4),
		('BOTTOMPADDING', (0, 0), (-1, -1), 4),
	]))
	elements.append(info_table)
	elements.append(Spacer(1, 0.3*inch))
	
	# Terms and courses
	for term in transcript['terms']:
		elements.append(Paragraph(f"Term: {term['name']} ({term['start_date']} - {term['end_date']})", section_style))
		
		# Course table
		course_data = [['Course Code', 'Course Name', 'CH', 'Grade', 'Status']]
		for course_item in term['courses']:
			course = course_item['course']
			grade = course_item['grade']
			grade_label = grade['letter_grade'] if grade['letter_grade'] else 'N/A'
			course_data.append([
				course['code'],
				course['name'][:40] + ('...' if len(course['name']) > 40 else ''),
				str(course['credit_hours']),
				grade_label,
				course_item['status'].title()
			])
		
		course_table = Table(course_data, colWidths=[1*inch, 2.5*inch, 0.6*inch, 0.8*inch, 1*inch])
		course_table.setStyle(TableStyle([
			('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
			('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
			('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
			('FONTSIZE', (0, 0), (-1, 0), 9),
			('FONTSIZE', (0, 1), (-1, -1), 8),
			('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
			('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
			('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
			('TOPPADDING', (0, 0), (-1, -1), 4),
			('BOTTOMPADDING', (0, 0), (-1, -1), 4),
		]))
		elements.append(course_table)
		
		# Term statistics
		stats = term['statistics']
		term_gpa = stats['term_gpa'] if stats['term_gpa'] is not None else 'N/A'
		elements.append(Spacer(1, 0.1*inch))
		elements.append(Paragraph(
			f"<b>Term Summary:</b> Attempted CH={stats['attempted_credit_hours']}, "
			f"Earned CH={stats['earned_credit_hours']}, <b>GPA={term_gpa}</b>",
			header_style
		))
		elements.append(Spacer(1, 0.2*inch))
	
	# Cumulative summary
	elements.append(PageBreak())
	elements.append(Paragraph("Cumulative Summary", section_style))
	
	summary = transcript['summary']
	cumulative_gpa = summary['cumulative_gpa'] if summary['cumulative_gpa'] is not None else 'N/A'
	
	summary_data = [
		['Cumulative Attempted Credit Hours:', str(summary['attempted_credit_hours'])],
		['Cumulative Earned Credit Hours:', str(summary['earned_credit_hours'])],
		['Cumulative GPA:', str(cumulative_gpa)],
		['Academic Standing:', student.get('academic_standing', 'N/A').title()],
	]
	summary_table = Table(summary_data, colWidths=[3*inch, 3*inch])
	summary_table.setStyle(TableStyle([
		('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
		('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
		('FONTSIZE', (0, 0), (-1, -1), 10),
		('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2d3748')),
		('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#edf2f7')),
		('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
		('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
		('TOPPADDING', (0, 0), (-1, -1), 8),
		('BOTTOMPADDING', (0, 0), (-1, -1), 8),
	]))
	elements.append(summary_table)
	
	# Footer
	elements.append(Spacer(1, 0.5*inch))
	elements.append(Paragraph(
		"<i>This is an official document generated by UniOne University system.</i>",
		ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#718096'), alignment=1)
	))
	
	doc.build(elements)
	buffer.seek(0)
	return buffer.getvalue()
