% ============================================================================
% HOLIDAY PACKAGES POLICY - ASP ENCODING
% ============================================================================
% This file encodes TUI holiday booking policy rules in Answer Set Programming
% for automated validation of LLM responses
% ============================================================================

% ----------------------------------------------------------------------------
% INPUT PREDICATES (ground facts supplied by the LLM fact extractor)
% Parsed by scripts/generate_vocabulary.py to auto-generate EXTRACTION_PROMPT.
% Format: @input  predicate_name/arity  arg1 arg2 ...  # description
% ----------------------------------------------------------------------------
% @input  customer/1           CustID                           # Customer identifier
% @input  booking/2            CustID BookID                    # Booking relationship
% @input  age/2                CustID Age                       # Customer age (integer years)
% @input  has_adult_companion/1 CustID                          # Minor has adult companion
% @input  days_until_holiday/2 BookID Days                      # Days until departure (integer)
% @input  paid_full/2          CustID BookID                    # Full balance paid
% @input  includes_flight/1    BookID                           # Booking includes a flight
% @input  complaint_filed_days/3 CustID BookID Days             # Days after return complaint filed
% @input  injury_claim_filed_days/3 CustID BookID Days          # Days after incident injury filed
% @input  llm_approves_booking/2  CustID BookID                 # LLM says booking is valid
% @input  llm_rejects_booking/2   CustID BookID                 # LLM says booking is invalid
% @input  llm_claims_cancellation_fee/3  CustID BookID Percent  # LLM claims cancellation % fee
% @input  llm_claims_fee/4     CustID BookID FeeType AmountPence # LLM claims amendment fee (pence)
% @input  llm_claims_atol_protected/2   CustID BookID           # LLM claims ATOL financial protection applies
% @input  llm_claims_abta_protected/2   CustID BookID           # LLM claims ABTA financial protection applies
% @input  llm_claims_amendment_blocked/3 CustID BookID ChangeType # LLM says this change is treated as cancellation
% ----------------------------------------------------------------------------

% ----------------------------------------------------------------------------
% DOMAIN DEFINITIONS
% ----------------------------------------------------------------------------

% Entity types
customer(C) :- booking(C, _).
booking_id(B) :- booking(_, B).

% ----------------------------------------------------------------------------
% IDENTITY & AGE REQUIREMENTS
% ----------------------------------------------------------------------------

% Lead name is valid unless proven invalid (Closed World: absence of age data
% means no age violation — only explicit age < 18 invalidates the lead name).
% ISS-007: was `lead_name_valid(C) :- customer(C), age(C, Age), Age >= 18.`
%          which required age to be supplied even for non-age queries.
lead_name_valid(C) :- customer(C), not lead_name_invalid(C, _).
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

% Name change: £25 at any time — no days required (ISS-009)
amendment_fee(C, B, "name_change", 2500) :- booking(C, B).

% Service upgrade: FREE at any time — no days required (ISS-009)
amendment_fee(C, B, "upgrade_service", 0) :- booking(C, B).

% Duration change: £50 (requires days_until_holiday for context)
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

% Booking invalid: minor lead booker WITHOUT adult companion (ISS-008)
% If minor_accompanied fires (has_adult_companion present), this rule does NOT fire.
% This allows TC003-style scenarios (minor + adult companion) to pass without
% triggering answer_invalid when the LLM approves.
% Note: the ASP model cannot verify WHO the lead name is in multi-person bookings.
booking_invalid(C, B, "Minor lead booker without adult companion") :-
    booking(C, B), lead_name_invalid(C, _), not minor_accompanied(C).

booking_invalid(C, B, Reason) :-
    booking(C, B), minor_unaccompanied(C, Reason).

booking_invalid(C, B, "Payment overdue - balance not paid within 84 days of departure") :-
    booking(C, B), payment_overdue(C, B).

% ============================================================================
% LLM ANSWER VALIDATION LAYER
% ============================================================================
% Validates LLM claims against symbolically derived policy facts.
% Only atoms in VIOLATION_PREFIXES (asp_validator.py) count as violations.
% Intermediate derived facts (booking_invalid, complaint_invalid, etc.) are
% NOT violations on their own — they are internal ASP computations.
% ============================================================================

% Overall answer validation
answer_valid(C, B) :-
    llm_approves_booking(C, B),
    booking_valid(C, B).

% LLM approved an invalid booking (hallucination / policy violation)
answer_invalid(C, B, "LLM approved invalid booking") :-
    llm_approves_booking(C, B),
    booking_invalid(C, B, _).

% LLM rejected a valid booking (false negative)
answer_invalid(C, B, "LLM rejected valid booking") :-
    llm_rejects_booking(C, B),
    booking_valid(C, B).

% Amendment fee validation
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

% ATOL/ABTA claim validation (ISS-010)
% Fires when LLM claims protection that is NOT supported by the booking facts.
atol_claim_incorrect(C, B, "LLM claims ATOL protection but booking has no flight") :-
    llm_claims_atol_protected(C, B),
    not includes_flight(B).

abta_claim_incorrect(C, B, "LLM claims ABTA protection but booking includes a flight") :-
    llm_claims_abta_protected(C, B),
    includes_flight(B).

% Amendment-blocked claim validation (ISS-010)
% Fires when LLM says an amendment is treated as cancellation but it actually is not.
amendment_assessment_correct(C, B, Type) :-
    llm_claims_amendment_blocked(C, B, Type),
    amendment_blocked(C, B, Type, _).

amendment_assessment_incorrect(C, B, Type, "LLM says change is blocked but amendment is allowed") :-
    llm_claims_amendment_blocked(C, B, Type),
    not amendment_blocked(C, B, Type, _).

% Display violations and validations
#show answer_invalid/3.
#show answer_valid/2.
#show fee_claim_incorrect/5.
#show cancellation_claim_incorrect/4.
#show atol_claim_incorrect/3.
#show abta_claim_incorrect/3.
#show amendment_assessment_incorrect/4.
#show amendment_assessment_correct/3.
