from rest_framework import serializers

from .models import Department, Faculty, University


class UniversitySerializer(serializers.ModelSerializer):
    class Meta:
        model = University
        fields = [
            'id',
            'name',
            'code',
            'country',
            'city',
            'established_year',
            'email',
            'phone',
            'website',
            'address',
        ]


class FacultySerializer(serializers.ModelSerializer):
    university = UniversitySerializer(read_only=True)

    class Meta:
        model = Faculty
        fields = ['id', 'name', 'name_ar', 'code', 'university']


class DepartmentSerializer(serializers.ModelSerializer):
    faculty = FacultySerializer(read_only=True)

    class Meta:
        model = Department
        fields = [
            'id',
            'name',
            'name_ar',
            'code',
            'scope',
            'is_mandatory',
            'required_credit_hours',
            'faculty',
        ]
