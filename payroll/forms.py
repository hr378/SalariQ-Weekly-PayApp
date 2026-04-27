from django import forms
from django.forms import inlineformset_factory

from .models import Activity, PayoutBatch, PayrollWeek, RateRule, Site, WorkRecord, WorkRecordAssignment, Worker


class DateInput(forms.DateInput):
    input_type = "date"


class WorkerForm(forms.ModelForm):
    class Meta:
        model = Worker
        fields = [
            "full_name",
            "national_id",
            "phone_number",
            "mpesa_phone",
            "gender",
            "home_site",
            "worker_category",
            "job_type",
            "nhif_number",
            "nssf_number",
            "status",
            "date_joined",
            "supervisor_name",
            "notes",
        ]
        widgets = {
            "date_joined": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = [
            "code",
            "name",
            "department",
            "supervisor_name",
            "payroll_model",
            "default_payment_method",
            "approval_chain",
            "is_active",
        ]
        widgets = {
            "approval_chain": forms.Textarea(attrs={"rows": 3, "placeholder": '["Supervisor", "Payroll Officer", "Finance"]'}),
        }


class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = [
            "code",
            "name",
            "description",
            "unit_of_measure",
            "rate_model",
            "max_manpower",
            "default_rate",
            "fixed_amount",
            "is_active",
            "sites",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "sites": forms.CheckboxSelectMultiple(),
        }


class RateRuleForm(forms.ModelForm):
    class Meta:
        model = RateRule
        fields = [
            "site",
            "activity",
            "effective_from",
            "effective_to",
            "model",
            "unit_rate",
            "fixed_amount",
            "pooled_amount",
            "max_manpower",
            "weighting_mode",
            "parameter_notes",
            "is_active",
        ]
        widgets = {
            "effective_from": DateInput(),
            "effective_to": DateInput(),
            "parameter_notes": forms.Textarea(attrs={"rows": 3}),
        }


class PayrollWeekForm(forms.ModelForm):
    class Meta:
        model = PayrollWeek
        fields = ["start_date", "end_date", "status", "active_sites"]
        widgets = {
            "start_date": DateInput(),
            "end_date": DateInput(),
            "active_sites": forms.CheckboxSelectMultiple(),
        }


class WorkRecordForm(forms.ModelForm):
    class Meta:
        model = WorkRecord
        fields = [
            "week",
            "site",
            "work_date",
            "shift",
            "truck_number",
            "client_details",
            "activity",
            "quantity",
            "manual_total_amount",
            "rate_rule",
            "payment_category",
            "remarks",
            "status",
        ]
        widgets = {
            "work_date": DateInput(),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }


class WorkRecordAssignmentForm(forms.ModelForm):
    class Meta:
        model = WorkRecordAssignment
        fields = ["worker", "role_label", "weight", "manual_amount", "notes"]


WorkRecordAssignmentFormSet = inlineformset_factory(
    WorkRecord,
    WorkRecordAssignment,
    form=WorkRecordAssignmentForm,
    extra=3,
    can_delete=True,
)


class PayoutBatchForm(forms.ModelForm):
    class Meta:
        model = PayoutBatch
        fields = ["week", "site", "payment_method", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class CommentForm(forms.Form):
    comments = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
