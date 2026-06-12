% ============================================================================
% HOLIDAY PACKAGES POLICY - ASP ENCODING
% ============================================================================
% This file encodes TUI holiday booking policy rules in Answer Set Programming
% for automated validation of LLM responses
% ============================================================================

% ----------------------------------------------------------------------------
% DOMAIN DEFINITIONS
% ----------------------------------------------------------------------------

% Entity types
customer(C) :- booking(C, _).
booking_id(B) :- booking(_, B).

% ----------------------------------------------------------------------------
% IDENTITY & AGE REQUIREMENTS
% ----------------------------------------------------------------------------

% Lead name must be an adult (18+)
lead_name_valid(C) :- customer(C), age(C, Age), Age >= 18.
lead_name_invalid(C, "Lead booker must be 18 or older") :- 
    customer(C), age(C, Age), Age < 18.

% Minors must be accompanied by adults
minor_accompanied(C) :- 
    customer(C), age(C, Age), Age < 18, has_adult_companion(C).

minor_unaccompanied(C, "Travelers under 18 must be accompanied by an adult") :- 
    customer(C), age(C, Age), Age < 18, not has_adult_companion(C).

% ----------------------------------------------------------------------------
% PAYMENT REQUIREMENTS
% ----------------------------------------------------------------------------

% Deposit required if booking >84 days before departure
payment_required_deposit(C, B) :- 
    booking(C, B), days_until_holiday(B, Days), Days > 84.

% Full payment required if booking ≤84 days before departure
payment_required_full(C, B) :- 
    booking(C, B), days_until_holiday(B, Days), Days <= 84.

% Balance overdue if within 84 days and not fully paid
balance_due(C, B) :- 
    booking(C, B), 
    days_until_holiday(B, Days), Days <= 84, 
    not paid_full(C, B).

payment_overdue(C, B) :- balance_due(C, B).

% ----------------------------------------------------------------------------
% AMENDMENT FEES (in pence)
% ----------------------------------------------------------------------------

% Name change: £25 at any time
amendment_fee(C, B, "name_change", 2500) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 0.

% Service upgrade: FREE
amendment_fee(C, B, "upgrade_service", 0) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 0.

% Duration change: £50
amendment_fee(C, B, "change_duration", 5000) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 0.

% Accommodation change: £50 if ≥29 days before departure
amendment_fee(C, B, "change_accommodation", 5000) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 29.

% ----------------------------------------------------------------------------
% AMENDMENT RESTRICTIONS
% ----------------------------------------------------------------------------

% Major changes <29 days treated as cancellation
amendment_blocked(C, B, Type, "Treated as cancellation - major change within 29 days") :- 
    booking(C, B), 
    days_until_holiday(B, Days), Days < 29,
    major_change(Type).

% Date postponement <70 days treated as cancellation
amendment_blocked(C, B, "later_date", "Treated as cancellation - postponement within 70 days") :- 
    booking(C, B), 
    days_until_holiday(B, Days), Days < 70.

% Define what constitutes a major change
major_change("change_accommodation").
major_change("change_destination").
major_change("later_date").

% ----------------------------------------------------------------------------
% CANCELLATION FEES (as percentage of total cost)
% ----------------------------------------------------------------------------

% ≥70 days: 0% (full refund minus deposit)
cancellation_fee_percent(C, B, 0) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 70.

% 63-69 days: 30%
cancellation_fee_percent(C, B, 30) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 63, Days < 70.

% 49-62 days: 50%
cancellation_fee_percent(C, B, 50) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 49, Days < 63.

% 29-48 days: 70%
cancellation_fee_percent(C, B, 70) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 29, Days < 49.

% 15-28 days: 90%
cancellation_fee_percent(C, B, 90) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 15, Days < 29.

% 0-14 days: 100% (no refund)
cancellation_fee_percent(C, B, 100) :- 
    booking(C, B), days_until_holiday(B, Days), Days < 15.

% Fee waived in extraordinary circumstances
cancellation_fee_waived(C, B, "Extraordinary circumstances at destination") :- 
    booking(C, B), extraordinary_circumstances_at_destination(B).

% ----------------------------------------------------------------------------
% COMPANY CANCELLATION COMPENSATION (when company cancels)
% ----------------------------------------------------------------------------

% ≥84 days: £0
company_cancellation_compensation_pence(C, B, 0) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 84.

% 29-83 days: £25
company_cancellation_compensation_pence(C, B, 2500) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 29, Days < 84.

% 15-28 days: £35
company_cancellation_compensation_pence(C, B, 3500) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 15, Days < 29.

% 8-14 days: £50
company_cancellation_compensation_pence(C, B, 5000) :- 
    booking(C, B), days_until_holiday(B, Days), Days >= 8, Days < 15.

% 0-7 days: £100
company_cancellation_compensation_pence(C, B, 10000) :- 
    booking(C, B), days_until_holiday(B, Days), Days < 8.

% Compensation waived in certain conditions
compensation_waived(C, B, "Events beyond company control") :- 
    booking(C, B), events_beyond_control(B).

compensation_waived(C, B, "Customer failed to pay required amount") :- 
    booking(C, B), not paid_required_amount(C, B).

% ----------------------------------------------------------------------------
% BEHAVIOR & CONDUCT
% ----------------------------------------------------------------------------

% Disruptive behavior consequences
disruptive_behavior_consequence(C, B, "Booking cancelled without refund") :- 
    booking(C, B), disruptive_before_departure(C).

disruptive_behavior_consequence(C, B, "Removed from accommodation without refund") :- 
    booking(C, B), disruptive_during_holiday(C).

disruptive_behavior_consequence(C, B, "No refund for any costs") :- 
    booking(C, B), disruptive_behavior(C).

% ----------------------------------------------------------------------------
% COMPLAINT & CLAIM TIME LIMITS
% ----------------------------------------------------------------------------

% General complaints: must file within 28 days of return
complaint_valid(C, B) :- 
    booking(C, B), complaint_filed_days(C, B, Days), Days <= 28.

complaint_invalid(C, B, "Complaint filed more than 28 days after return") :- 
    booking(C, B), complaint_filed_days(C, B, Days), Days > 28.

% Personal injury claims: must file within 90 days (3 months)
injury_claim_valid(C, B) :- 
    booking(C, B), injury_claim_filed_days(C, B, Days), Days <= 90.

injury_claim_invalid(C, B, "Injury claim filed more than 90 days after incident") :- 
    booking(C, B), injury_claim_filed_days(C, B, Days), Days > 90.

% ----------------------------------------------------------------------------
% FINANCIAL PROTECTION
% ----------------------------------------------------------------------------

% ATOL protection for packages including flights
atol_protected(C, B) :- booking(C, B), includes_flight(B).

% ABTA protection for packages without flights
abta_protected(C, B) :- booking(C, B), not includes_flight(B).

% ----------------------------------------------------------------------------
% BOOKING VALIDATION (Overall Status)
% ----------------------------------------------------------------------------

% Booking is valid if all requirements met
booking_valid(C, B) :- 
    booking(C, B),
    lead_name_valid(C),
    not minor_unaccompanied(C, _),
    not payment_overdue(C, B).

% Booking invalid if any critical requirement fails
booking_invalid(C, B, Reason) :- 
    booking(C, B), lead_name_invalid(C, Reason).

booking_invalid(C, B, Reason) :- 
    booking(C, B), minor_unaccompanied(C, Reason).

booking_invalid(C, B, "Payment overdue - balance not paid within 84 days of departure") :- 
    booking(C, B), payment_overdue(C, B).

% ============================================================================
% LLM ANSWER VALIDATION LAYER
% ============================================================================
% This section validates claims made by the LLM against policy rules
% ============================================================================

% Overall answer validation - LLM approves a valid booking
answer_valid(C, B) :- 
    llm_approves_booking(C, B),
    booking_valid(C, B).

% LLM approved an invalid booking
answer_invalid(C, B, "LLM approved invalid booking") :- 
    llm_approves_booking(C, B),
    booking_invalid(C, B, _).

% LLM rejected a valid booking
answer_invalid(C, B, "LLM rejected valid booking") :- 
    llm_rejects_booking(C, B),
    booking_valid(C, B).

% Fee calculation validation
fee_claim_correct(C, B, FeeType, Amount) :-
    llm_claims_fee(C, B, FeeType, Amount),
    amendment_fee(C, B, FeeType, Amount).

fee_claim_incorrect(C, B, FeeType, ClaimedAmount, "Incorrect fee amount") :-
    llm_claims_fee(C, B, FeeType, ClaimedAmount),
    amendment_fee(C, B, FeeType, ActualAmount),
    ClaimedAmount != ActualAmount.

% Cancellation fee validation
cancellation_claim_correct(C, B, Percent) :-
    llm_claims_cancellation_fee(C, B, Percent),
    cancellation_fee_percent(C, B, Percent).

cancellation_claim_incorrect(C, B, ClaimedPercent, "Incorrect cancellation fee") :-
    llm_claims_cancellation_fee(C, B, ClaimedPercent),
    cancellation_fee_percent(C, B, ActualPercent),
    ClaimedPercent != ActualPercent.

% Display violations for debugging
#show llm_claim_invalid/3.
#show answer_invalid/3.
#show fee_claim_incorrect/5.
#show cancellation_claim_incorrect/4.
#show answer_valid/2.
