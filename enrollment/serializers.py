from rest_framework import serializers

class StudentProfileSerializer(serializers.Serializer):
	student_number = serializers.CharField()
	faculty = serializers.CharField()
	department = serializers.CharField()
	gpa = serializers.DecimalField(max_digits=3, decimal_places=2)
	standing = serializers.CharField()


class EnrollmentSerializer(serializers.Serializer):
	id = serializers.IntegerField()
	status = serializers.CharField()
	registered_at = serializers.DateTimeField()
	section = serializers.JSONField()


class GradeSerializer(serializers.Serializer):
	id = serializers.IntegerField()
	points = serializers.IntegerField()
	letter_grade = serializers.CharField()
	status = serializers.CharField()
	academic_term = serializers.JSONField()
	course = serializers.JSONField()