% Domain definition
customer(C) :- booking(C, _).
booking_id(B) :- booking(_, B).
holiday_type(T) :- booking_type(_, T).

% Lead name requirements
lead_name_valid(C) :- customer(C), age(C, Age), Age >= 18.
lead_name_invalid(C, "Must be adult") :- customer(C), age(C, Age), Age < 18.

% Minor accompaniment rules
minor_accompanied(C) :- customer(C), age(C, Age), Age < 18, has_adult_companion(C).
minor_unaccompanied(C, "Under 18 must be accompanied by adult") :- customer(C), age(C, Age), Age < 18, not has_adult_companion(C).

% Payment requirements
payment_required_deposit(C, B) :- booking(C, B), days_until_holiday(B, Days), Days > 84.
payment_required_full(C, B) :- booking(C, B), days_until_holiday(B, Days), Days <= 84.
balance_due(C, B) :- booking(C, B), days_until_holiday(B, Days), Days <= 84, not paid_full(C, B).

% Amendment fees in pence (multiplied by 100)
amendment_fee(C, B, "name_change", 2500) :- booking(C, B), days_until_holiday(B, Days), Days >= 0.
amendment_fee(C, B, "upgrade_service", 0) :- booking(C, B), days_until_holiday(B, Days), Days >= 0.
amendment_fee(C, B, "change_duration", 5000) :- booking(C, B), days_until_holiday(B, Days), Days >= 0.
amendment_fee(C, B, "change_accommodation", 5000) :- booking(C, B), days_until_holiday(B, Days), Days >= 29.

% Amendment restrictions
amendment_blocked(C, B, Type, "Treated as cancellation") :- booking(C, B), days_until_holiday(B, Days), Days < 29, change_type(Type), major_change(Type).
amendment_blocked(C, B, "later_date", "Treated as cancellation") :- booking(C, B), days_until_holiday(B, Days), Days < 70.

% Major change types
major_change("change_accommodation").
major_change("change_destination").
major_change("later_date").

% Cancellation fees as percentages
cancellation_fee_percent(C, B, 0) :- booking(C, B), days_until_holiday(B, Days), Days >= 70.
cancellation_fee_percent(C, B, 30) :- booking(C, B), days_until_holiday(B, Days), Days >= 63, Days < 70.
cancellation_fee_percent(C, B, 50) :- booking(C, B), days_until_holiday(B, Days), Days >= 49, Days < 63.
cancellation_fee_percent(C, B, 70) :- booking(C, B), days_until_holiday(B, Days), Days >= 29, Days < 49.
cancellation_fee_percent(C, B, 90) :- booking(C, B), days_until_holiday(B, Days), Days >= 15, Days < 29.
cancellation_fee_percent(C, B, 100) :- booking(C, B), days_until_holiday(B, Days), Days < 15.

% Cancellation fee exemptions
cancellation_fee_waived(C, B, "Extraordinary circumstances") :- booking(C, B), extraordinary_circumstances_at_destination(B).

% Company cancellation compensation in pence
company_cancellation_compensation_pence(C, B, 0) :- booking(C, B), days_until_holiday(B, Days), Days >= 84.
company_cancellation_compensation_pence(C, B, 2500) :- booking(C, B), days_until_holiday(B, Days), Days >= 29, Days < 84.
company_cancellation_compensation_pence(C, B, 3500) :- booking(C, B), days_until_holiday(B, Days), Days >= 15, Days < 29.
company_cancellation_compensation_pence(C, B, 5000) :- booking(C, B), days_until_holiday(B, Days), Days >= 8, Days < 15.
company_cancellation_compensation_pence(C, B, 10000) :- booking(C, B), days_until_holiday(B, Days), Days < 8.

% Compensation exemptions
compensation_waived(C, B, "Events beyond control") :- booking(C, B), events_beyond_control(B).
compensation_waived(C, B, "Customer non-payment") :- booking(C, B), not paid_required_amount(C, B).

% Behavior restrictions
disruptive_behavior_consequence(C, B, "Booking cancelled") :- booking(C, B), disruptive_before_departure(C).
disruptive_behavior_consequence(C, B, "Removed from accommodation") :- booking(C, B), disruptive_during_holiday(C).
disruptive_behavior_consequence(C, B, "No refund") :- booking(C, B), disruptive_behavior(C).

% Complaint time limits in days
complaint_valid(C, B) :- booking(C, B), complaint_filed_days(C, B, Days), Days <= 28.
complaint_invalid(C, B, "Filed too late") :- booking(C, B), complaint_filed_days(C, B, Days), Days > 28.

% Personal injury claim time limits in days (3 months = 90 days)
injury_claim_valid(C, B) :- booking(C, B), injury_claim_filed_days(C, B, Days), Days <= 90.
injury_claim_invalid(C, B, "Filed too late") :- booking(C, B), injury_claim_filed_days(C, B, Days), Days > 90.

% Financial protection
atol_protected(C, B) :- booking(C, B), includes_flight(B).
abta_protected(C, B) :- booking(C, B), not includes_flight(B).

% Final booking status
booking_valid(C, B) :- booking(C, B), lead_name_valid(C), not minor_unaccompanied(C, _), not payment_overdue(C, B).
booking_invalid(C, B, Reason) :- booking(C, B), lead_name_invalid(C, Reason).
booking_invalid(C, B, Reason) :- booking(C, B), minor_unaccompanied(C, Reason).
booking_invalid(C, B, "Payment overdue") :- booking(C, B), payment_overdue(C, B).
