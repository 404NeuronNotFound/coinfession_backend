from django.contrib.auth.models import User
from rest_framework import serializers
from .models import UserProfile


class UserSerializers(serializers.ModelSerializer):
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'id', 
            'username', 
            'first_name', 
            'last_name', 
            'email',
            'password',
            'confirm_password'
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = User.objects.create_user(**validated_data)
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'username',
            'email',
            'first_name',
            'last_name',
            'display_name',
            'bio',
            'profile_photo_url',
            'currency',
            'timezone',
            'member_since',
        ]
        read_only_fields = [
            'username',
            'email',
            'first_name',
            'last_name',
            'member_since',
        ]


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            'display_name',
            'bio',
            'profile_photo_url',
            'currency',
            'timezone',
        ]


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    confirm_password = serializers.CharField(write_only=True, required=True)

    def validate(self, data):
        user = self.context['request'].user
        
        if not user.check_password(data['current_password']):
            raise serializers.ValidationError({
                'current_password': 'Current password is incorrect.'
            })
        
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': 'New passwords do not match.'
            })
        
        if user.check_password(data['new_password']):
            raise serializers.ValidationError({
                'new_password': 'New password must be different from current password.'
            })
        
        if len(data['new_password']) < 8:
            raise serializers.ValidationError({
                'new_password': 'Password must be at least 8 characters long.'
            })
        
        return data
