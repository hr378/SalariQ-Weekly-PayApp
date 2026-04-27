from django.urls import path

from . import views


urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("workers/", views.WorkerListView.as_view(), name="worker-list"),
    path("workers/new/", views.WorkerCreateView.as_view(), name="worker-create"),
    path("workers/<int:pk>/", views.WorkerDetailView.as_view(), name="worker-detail"),
    path("workers/<int:pk>/edit/", views.WorkerUpdateView.as_view(), name="worker-update"),
    path("sites/", views.SiteListView.as_view(), name="site-list"),
    path("sites/new/", views.SiteCreateView.as_view(), name="site-create"),
    path("sites/<int:pk>/edit/", views.SiteUpdateView.as_view(), name="site-update"),
    path("activities/", views.ActivityListView.as_view(), name="activity-list"),
    path("activities/new/", views.ActivityCreateView.as_view(), name="activity-create"),
    path("activities/<int:pk>/edit/", views.ActivityUpdateView.as_view(), name="activity-update"),
    path("rate-rules/", views.RateRuleListView.as_view(), name="rate-rule-list"),
    path("rate-rules/new/", views.RateRuleCreateView.as_view(), name="rate-rule-create"),
    path("rate-rules/<int:pk>/edit/", views.RateRuleUpdateView.as_view(), name="rate-rule-update"),
    path("weeks/", views.PayrollWeekListView.as_view(), name="week-list"),
    path("weeks/new/", views.PayrollWeekCreateView.as_view(), name="week-create"),
    path("weeks/<int:pk>/", views.PayrollWeekDetailView.as_view(), name="week-detail"),
    path("weeks/<int:pk>/edit/", views.PayrollWeekUpdateView.as_view(), name="week-update"),
    path("weeks/<int:pk>/recalculate/", views.recalculate_week_view, name="week-recalculate"),
    path("weeks/<int:pk>/submit/", views.submit_week_view, name="week-submit"),
    path("weeks/<int:pk>/approve/", views.approve_week_view, name="week-approve"),
    path("weeks/<int:pk>/return/", views.return_week_view, name="week-return"),
    path("records/", views.WorkRecordListView.as_view(), name="work-record-list"),
    path("records/new/", views.work_record_form_view, name="work-record-create"),
    path("records/<int:pk>/edit/", views.work_record_form_view, name="work-record-update"),
    path("records/<int:pk>/submit/", views.submit_record_view, name="work-record-submit"),
    path("payouts/", views.PayoutBatchListView.as_view(), name="payout-batch-list"),
    path("payouts/new/", views.payout_batch_create_view, name="payout-batch-create"),
    path("payouts/<int:pk>/", views.PayoutBatchDetailView.as_view(), name="payout-batch-detail"),
    path("payouts/<int:pk>/export/", views.export_payout_batch_csv, name="payout-batch-export"),
    path("payouts/<int:pk>/paid/", views.mark_payout_batch_paid, name="payout-batch-paid"),
    path("reports/", views.reports_view, name="reports"),
]
