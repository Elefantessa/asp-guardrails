% Domain definition - booking and customer entities
booking(B) :- lead_name(B, _).
customer(C) :- lead_name(B, C).
passenger(B, P) :- booking(B), passenger_on_booking(B, P).

% Age requirements
adult(P) :- age(P, Age), Age >= 18.
minor(P) :- age(P, Age), Age < 18.

% Booking validity - lead name must be adult
valid_booking(B) :- booking(B), lead_name(B, C), adult(C).
invalid_booking(B, "Lead name must be adult") :- booking(B), lead_name(B, C), minor(C).

% Minor accompaniment requirement
minor_accompanied(B, P) :- booking(B), minor(P), passenger_on_booking(B, P), passenger_on_booking(B, A), adult(A).
unaccompanied_minor(B, P, "Minor must be accompanied by adult") :- booking(B), minor(P), passenger_on_booking(B, P), not minor_accompanied(B, P).

% Payment requirements
deposit_required(B) :- booking(B), days_before_departure(B, Days), Days > 84.
full_payment_required(B) :- booking(B), days_before_departure(B, Days), Days <= 84.
balance_due(B) :- booking(B), days_before_departure(B, Days), Days <= 84, Days > 0, not full_payment_made(B).

% Payment status
payment_valid(B) :- deposit_required(B), deposit_paid(B).
payment_valid(B) :- full_payment_required(B), full_payment_made(B).
payment_invalid(B, "Deposit required") :- deposit_required(B), not deposit_paid(B).
payment_invalid(B, "Full payment required") :- full_payment_required(B), not full_payment_made(B).
payment_invalid(B, "Balance payment overdue") :- balance_due(B).

% Amendment fees in GBP cents
amendment_fee_cents(B, "name_change", 2500) :- booking(B), days_before_departure(B, Days), Days >= 0.
amendment_fee_cents(B, "upgrade_service", 0) :- booking(B), days_before_departure(B, Days), Days >= 0.
amendment_fee_cents(B, "change_duration", 5000) :- booking(B), days_before_departure(B, Days), Days >= 0.
amendment_fee_cents(B, "change_flight_time", 5000) :- booking(B), days_before_departure(B, Days), Days >= 0.
amendment_fee_cents(B, "change_accommodation", 5000) :- booking(B), days_before_departure(B, Days), Days >= 29.
amendment_fee_cents(B, "change_airport", 5000) :- booking(B), days_before_departure(B, Days), Days >= 29.
amendment_fee_cents(B, "travel_earlier", 5000) :- booking(B), days_before_departure(B, Days), Days >= 0.
amendment_fee_cents(B, "travel_later", 5000) :- booking(B), days_before_departure(B, Days), Days >= 70.

% Amendment treated as cancellation
amendment_as_cancellation(B, "change_accommodation") :- booking(B), days_before_departure(B, Days), Days < 29.
amendment_as_cancellation(B, "change_airport") :- booking(B), days_before_departure(B, Days), Days < 29.
amendment_as_cancellation(B, "travel_later") :- booking(B), days_before_departure(B, Days), Days < 70.

% Cancellation fee percentages (as integers)
cancellation_fee_percent(B, 100) :- booking(B), days_before_departure(B, Days), Days >= 70.
cancellation_fee_percent(B, 30) :- booking(B), days_before_departure(B, Days), Days >= 63, Days < 70.
cancellation_fee_percent(B, 50) :- booking(B), days_before_departure(B, Days), Days >= 49, Days < 63.
cancellation_fee_percent(B, 70) :- booking(B), days_before_departure(B, Days), Days >= 29, Days < 49.
cancellation_fee_percent(B, 90) :- booking(B), days_before_departure(B, Days), Days >= 15, Days < 29.
cancellation_fee_percent(B, 100) :- booking(B), days_before_departure(B, Days), Days < 15.

% Cancellation fee waiver for extraordinary circumstances
cancellation_fee_waived(B) :- booking(B), unavoidable_extraordinary_circumstance(B).

% Compensation for company cancellation in GBP cents
company_cancellation_compensation_cents(B, 0) :- booking(B), days_before_departure(B, Days), Days >= 84.
company_cancellation_compensation_cents(B, 2500) :- booking(B), days_before_departure(B, Days), Days >= 29, Days < 84.
company_cancellation_compensation_cents(B, 3500) :- booking(B), days_before_departure(B, Days), Days >= 15, Days < 29.
company_cancellation_compensation_cents(B, 5000) :- booking(B), days_before_departure(B, Days), Days >= 8, Days < 15.
company_cancellation_compensation_cents(B, 10000) :- booking(B), days_before_departure(B, Days), Days < 8.

% No compensation for events beyond control
no_compensation_event_beyond_control(B) :- booking(B), event_beyond_control(B).
no_compensation_non_payment(B) :- booking(B), payment_invalid(B, _).

% Major change definition
major_change(B, "destination_change") :- booking(B), destination_changed(B).
major_change(B, "accommodation_downgrade") :- booking(B), accommodation_downgraded_one_star(B).
major_change(B, "flight_time_change_12h") :- booking(B), flight_time_changed_hours(B, Hours), Hours > 12.
major_change(B, "departure_airport_change") :- booking(B), uk_departure_airport_changed(B).

% Major change compensation (same as company cancellation)
major_change_compensation_cents(B, Amount) :- booking(B), major_change(B, _), company_cancellation_compensation_cents(B, Amount).

% Child compensation is 50% of adult
child_compensation_cents(B, ChildAmount) :- booking(B), company_cancellation_compensation_cents(B, AdultAmount), ChildAmount = AdultAmount / 2.

% Disruptive behavior consequences
disruptive_passenger(B, P) :- booking(B), passenger_on_booking(B, P), behavior_disruptive(P).
booking_cancelled_disruption(B) :- booking(B), disruptive_passenger(B, P), boarding_refused(P).
removed_from_accommodation(B, P) :- booking(B), disruptive_passenger(B, P), on_holiday(B).
no_refund_disruption(B) :- booking(B), disruptive_passenger(B, _).

% Complaint timeline - must report within 28 days
complaint_valid(B) :- booking(B), complaint_filed(B), days_since_return(B, Days), Days <= 28.
complaint_invalid(B, "Complaint filed too late") :- booking(B), complaint_filed(B), days_since_return(B, Days), Days > 28.

% Personal injury claim timeline - must report within 3 months (90 days)
injury_claim_valid(B, P) :- booking(B), passenger_on_booking(B, P), injury_claim_filed(P), days_since_return(B, Days), Days <= 90.
injury_claim_invalid(B, P, "Claim filed too late") :- booking(B), passenger_on_booking(B, P), injury_claim_filed(P), days_since_return(B, Days), Days > 90.

% Transfer requirements - 7 days notice
transfer_allowed(B, P) :- booking(B), passenger_on_booking(B, P), transfer_notice_days(B, Days), Days >= 7.
transfer_not_allowed(B, P, "Insufficient notice") :- booking(B), passenger_on_booking(B, P), transfer_notice_days(B, Days), Days < 7.

% Reduced mobility notification - 48 hours before
mobility_notification_required(B, P) :- booking(B), passenger_on_booking(B, P), reduced_mobility(P).
mobility_notification_valid(B, P) :- mobility_notification_required(B, P), notification_hours_before(B, Hours), Hours >= 48.
mobility_notification_invalid(B, P, "Insufficient notice") :- mobility_notification_required(B, P), notification_hours_before(B, Hours), Hours < 48.

% Financial protection
atol_protected(B) :- booking(B), includes_flight(B).
abta_protected(B) :- booking(B), not includes_flight(B).
