#!/bin/bash
# Pass 4's mutation sample, as run: each line applies one mutation with mutate.sh, runs the tests named, restores the file.
# Run from the root of a detached worktree at the reviewed commit, never the shared tree. `-x` stops at the first failure.
set -u
M=reviews/2026-11/probes/mutate.sh
QUICK="$(ls tests/test_*.py | grep -v -E 'test_temporal|test_dev_server|test_doctor_live|test_skipping_server|retry_rejected|test_schema|audit_export|time_zones|vault_keys|test_layers|worker_threads|builder_types|test_package|thread_guard') -x"
FAST="$(ls tests/test_*.py | grep -v -E 'test_temporal|test_dev_server|test_doctor_live|test_skipping_server') -x"
ALL="tests -x"
$M core01_risk_not_checked_for_approver src/ventoux/core/approval.py '        and may_approve(catalog.roles[role], contract.risk)
' '        and True
' $QUICK
$M core02_approver_role_not_listed src/ventoux/core/approval.py '        if role in roles
' '        if True
' $QUICK
$M core03_own_answer_approves src/ventoux/core/approval.py 'if f"person:{person}" in sources.get(field, frozenset()):' 'if False:' $QUICK
$M core04_conditions_not_someone_else src/ventoux/core/approval.py '((inputs, f"{step} uses"), (conditions, f"decides whether {step} runs"))' '((inputs, f"{step} uses"),)' $QUICK
$M core05_digest_of_sensitive_plain src/ventoux/core/approval.py 'return Sensitive(digest) if read else digest' 'return digest' $QUICK
$M core06_digest_number_as_text src/ventoux/core/approval.py 'default=lambda number: {"number": str(number)}' default=str $QUICK
$M core07_key_given_by_definition src/ventoux/core/before_activity.py 'if contract.idempotency_key is not None and contract.idempotency_key in inputs:' 'if False:' $QUICK
$M core08_reference_wrong_system src/ventoux/core/before_activity.py 'if field in inputs and (wrong := not_a_reference_to(system, inputs[field], types)):' 'if False and (wrong := not_a_reference_to(system, inputs[field], types)):' $QUICK
$M core09_input_policy_not_checked src/ventoux/core/before_activity.py '            if policy.refuses(found) is not None:' '            if False:' $QUICK
$M core10_steering_not_checked src/ventoux/core/before_activity.py 'if policy.refuses(steering.sources) is not None:' 'if False:' $QUICK
$M core11_unknown_input_passed src/ventoux/core/before_activity.py '    if unknown:
' '    if False:
' $QUICK
$M core12_inputs_not_strict src/ventoux/core/before_activity.py 'model_validate(unwrapped(given), strict=True)' 'model_validate(unwrapped(given), strict=False)' $QUICK
$M core13_only_from_no_source src/ventoux/core/policy.py '        if not sources:
            return "it comes from no system"' '        if False:
            return "it comes from no system"' $QUICK
$M core14_only_from_union src/ventoux/core/policy.py 'systems = named if systems is None else systems & named' 'systems = named if systems is None else systems | named' $QUICK
$M core15_unknown_policy_kind src/ventoux/core/policy.py '        if type(policy) not in KINDS:' '        if False:' $QUICK
$M core16_within_any src/ventoux/core/policy.py '        return False  # an untrusted source is accepted by `inner` only' '        return True  # an untrusted source is accepted by `inner` only' $QUICK
$M core17_within_systems src/ventoux/core/policy.py 'return systems <= outer_systems' 'return systems >= outer_systems' $QUICK
$M core18_risk_strictly_below src/ventoux/core/roles.py 'return RISKS.index(risk) <= RISKS.index(approves)' 'return RISKS.index(risk) < RISKS.index(approves)' $QUICK
$M core19_unregistered_role_counts src/ventoux/core/roles.py 'if role in allowed and role in registered)' 'if role in allowed)' $QUICK
$M core20_longest_id_201 src/ventoux/core/form.py 'LONGEST_ID = 200' 'LONGEST_ID = 201' $QUICK
$M core21_most_items_101 src/ventoux/core/form.py 'MOST_ITEMS = 100' 'MOST_ITEMS = 101' $QUICK
$M core22_infinite_number_fits src/ventoux/core/form.py 'return isinstance(value, Decimal) and value.is_finite()' 'return isinstance(value, Decimal)' $QUICK
$M core23_empty_option_fits src/ventoux/core/form.py 'return isinstance(value, str) and value != ""' 'return isinstance(value, str)' $QUICK
$M core24_empty_attachment_fits src/ventoux/core/form.py '0 < len(value) <= LONGEST_ID' '0 <= len(value) <= LONGEST_ID' $QUICK
$M core25_form_extra_field src/ventoux/core/form.py '        if field not in sets:
' '        if False:
' $QUICK
$M core26_item_extra_field src/ventoux/core/form.py 'if any(name not in declared.fields for name in item):' 'if False:' $QUICK
$M core27_outcome_any_text src/ventoux/core/form.py 'return isinstance(value, str) and value in declared.outcomes' 'return isinstance(value, str)' $QUICK
$M core28_role_any_spelling src/ventoux/core/roles.py '    if not is_label(name):' '    if False:' $QUICK
$M core29_eq_coerces src/ventoux/core/expressions/evaluate.py '        if kind(left) != kind(right):' '        if False:' $QUICK
$M core30_in_coerces src/ventoux/core/expressions/evaluate.py '        if kind(found) != kind(options[0]):' '        if False:' $QUICK
$M core31_nonfinite_read src/ventoux/core/expressions/evaluate.py '    if isinstance(value, Decimal) and not value.is_finite():' '    if False:' $QUICK
$M core32_decimal128_not_checked src/ventoux/core/expressions/evaluate.py '    if isinstance(value, Decimal) and not fits_decimal128(value):' '    if False:' $QUICK
$M core33_truthy src/ventoux/core/expressions/evaluate.py '    if not isinstance(value, bool):
        verb = "takes a boolean"' '    if False:
        verb = "takes a boolean"' $QUICK
$M core34_div_zero_named src/ventoux/core/expressions/evaluate.py '        if isinstance(expression, Div) and numbers[1] == 0:' '        if False:' $QUICK
$M core35_moment_read src/ventoux/core/expressions/evaluate.py '    if isinstance(expression, date) and not is_day(expression):' '    if False:' $QUICK
$M core36_records_not_mappings src/ventoux/core/expressions/evaluate.py 'if not isinstance(held, list) or not all(isinstance(element, Mapping) for element in held):' 'if not isinstance(held, list):' $QUICK
$M core37_ge_as_gt src/ventoux/core/expressions/evaluate.py '        return a >= b' '        return a > b' $QUICK
$M core38_loop_bound_1001 src/ventoux/core/interpreter.py 'ENTRIES_WITHOUT_A_WAIT = 1000' 'ENTRIES_WITHOUT_A_WAIT = 1001' $QUICK
$M core39_undeclared_outcome src/ventoux/core/interpreter.py '        if outcome.name not in contract.outcomes:' '        if False:' $QUICK
$M core40_changed_inputs_approved src/ventoux/core/interpreter.py '        if now != approval.digest:' '        if False:' $QUICK
$M core41_high_risk_unapproved src/ventoux/core/interpreter.py '    if contract.risk == "high":
        raise Stop' '    if False:
        raise Stop' $QUICK
$M core42_approval_reused src/ventoux/core/interpreter.py 'approval = approvals.pop(here, None)' 'approval = approvals.get(here)' $QUICK
$M core43_identifier_not_checked src/ventoux/core/interpreter.py 'if answer.by is not None and (wrong := identifier_problem(answer.by)) is not None:' 'if False and (wrong := identifier_problem(answer.by)) is not None:' $QUICK
$M core44_excluded_approves src/ventoux/core/interpreter.py '    if by in excluded:' '    if False:' $QUICK
$M core45_untrusted_path src/ventoux/core/interpreter.py '        if untrusted:
            raise Stop(
                f"on {event}, the transition' '        if False:
            raise Stop(
                f"on {event}, the transition' $QUICK
$M core46_person_times_out src/ventoux/core/interpreter.py '        if answer.by is not None:
            return "a timeout comes' '        if False:
            return "a timeout comes' $QUICK
$M core47_unknown_outcome src/ventoux/core/interpreter.py '    if answer.outcome not in question.outcomes:' '    if False:' $QUICK
$M core48_case_source_given src/ventoux/core/interpreter.py '        elif CASE in given.sources:' '        elif False:' $QUICK
$M core49_no_sources_given src/ventoux/core/interpreter.py '        elif not given.sources:' '        elif False:' $QUICK
$M core50_condition_not_boolean src/ventoux/core/interpreter.py '    if not isinstance(decided, bool):' '    if False:' $QUICK
$M core51_v_untrusted_transition src/ventoux/core/validate.py '        if name in plan.sources:
            return [
                Issue(
                    path,
                    "UNTRUSTED_TRANSITION"' '        if False:
            return [
                Issue(
                    path,
                    "UNTRUSTED_TRANSITION"' $QUICK
$M core52_v_approval_role_risk src/ventoux/core/validate.py 'if role in catalog.roles and not may_approve(catalog.roles[role], contract.risk)' 'if False' $QUICK
$M core53_v_reserved_outcome src/ventoux/core/validate.py '    if TIMEOUT in state.wait.outcomes:' '    if False:' $QUICK
$M core54_v_approve_goes_elsewhere src/ventoux/core/validate.py '            if transition.target != of:' '            if False:' $QUICK
$M core55_v_engine_input src/ventoux/core/validate.py '        if name == key:
            issues.append(' '        if False:
            issues.append(' $QUICK
$M core56_v_missing_input src/ventoux/core/validate.py 'if field.is_required() and name not in state.inputs:' 'if False:' $QUICK
$M core57_v_condition_boolean src/ventoux/core/validate.py '    if condition and not isinstance(found, BooleanType):' '    if False:' $QUICK
$M core58_v_approval_required src/ventoux/core/validate.py 'if name in reached and isinstance(state, ActivityState) and is_high_risk(state, catalog):' 'if False:' $QUICK
$M core59_v_approval_reused src/ventoux/core/validate.py '        if again:' '        if False:' $QUICK
$M core60_v_sets_unknown_field src/ventoux/core/validate.py '            if field not in plan.fields:
                issues.append(' '            if False:
                issues.append(' $QUICK
$M tool01_vault_exportable src/ventoux/tooling/vault.py '        if config[setting] is not False:' '        if False:' tests/test_vault_keys.py tests/test_doctor.py
