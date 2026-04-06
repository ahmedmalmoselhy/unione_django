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
