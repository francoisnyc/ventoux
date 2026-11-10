#!/bin/bash
# Pass 4's mutation sample, as run: each line applies one mutation with mutate.sh, runs the tests named, restores the file.
# Run from the root of a detached worktree at the reviewed commit, never the shared tree. `-x` stops at the first failure.
set -u
M=reviews/2026-11/probes/mutate.sh
QUICK="$(ls tests/test_*.py | grep -v -E 'test_temporal|test_dev_server|test_doctor_live|test_skipping_server|retry_rejected|test_schema|audit_export|time_zones|vault_keys|test_layers|worker_threads|builder_types|test_package|thread_guard') -x"
REST="$(ls tests/test_*.py | grep -E 'retry_rejected|test_schema|audit_export|time_zones|vault_keys|test_layers|worker_threads|builder_types|test_package|thread_guard') -x"
TEMP="$(ls tests/test_temporal*.py) -x"
FAST="$(ls tests/test_*.py | grep -v -E 'test_temporal|test_dev_server|test_doctor_live|test_skipping_server') -x"
ALL="tests -x"
$M auth01_rounds_upper src/ventoux/authoring/loop.py 'ROUNDS = range(1, 6)' 'ROUNDS = range(1, 7)' tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py
$M auth02_rounds_lower src/ventoux/authoring/loop.py 'ROUNDS = range(1, 6)' 'ROUNDS = range(0, 6)' tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py
$M auth03_rounds_unchecked src/ventoux/authoring/loop.py '    if rounds not in ROUNDS:' '    if False:' tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py
$M auth04_extra_round src/ventoux/authoring/loop.py '    for _ in range(rounds):' '    for _ in range(rounds + 1):' tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py
$M auth05_failed_provider_retried src/ventoux/authoring/loop.py '            return Authored("no answer", None, tuple(done), why)' '            continue' tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py
$M auth06_abandoned_keeps_plan src/ventoux/authoring/loop.py '    return Authored(
        "abandoned",
        None,' '    return Authored(
        "abandoned",
        unfenced(done[-1].answer),' tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py
$M auth07_wrong_plan src/ventoux/authoring/loop.py '    if drafted != plan:' '    if False:' tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py
$M auth08_warnings_as_errors src/ventoux/authoring/loop.py '    errors = [said(issue) for issue in issues if is_error(issue)]' '    errors = []' tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py
$M auth09_step_naming src/ventoux/authoring/loop.py '        if isinstance(step, PlanStep) and step.plan == plan:' '        if isinstance(step, PlanStep):' tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py
$M auth10_key_twice src/ventoux/authoring/answers.py '    if repeated:
        raise NotOneObject' '    if False:
        raise NotOneObject' tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py tests/test_advisor.py
$M auth11_not_object src/ventoux/authoring/answers.py '    if not isinstance(read, dict):' '    if False:' tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py tests/test_advisor.py
$M auth12_unfenced_prose src/ventoux/authoring/answers.py '    if not (text.startswith("```") and text.endswith("```") and "\n" in text):' '    if not (text.startswith("```") or text.endswith("```")):' tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py tests/test_advisor.py
$M auth12_unfenced_prose@FAST src/ventoux/authoring/answers.py '    if not (text.startswith("```") and text.endswith("```") and "\n" in text):' '    if not (text.startswith("```") or text.endswith("```")):' $FAST
$M auth13_no_model src/ventoux/authoring/anthropic.py '        if not model:' '        if False:' tests/test_anthropic_provider.py tests/test_authoring.py tests/test_advisor.py
$M auth14_no_key src/ventoux/authoring/anthropic.py '        if not key:' '        if False:' tests/test_anthropic_provider.py tests/test_authoring.py tests/test_advisor.py
$M auth15_base_url src/ventoux/authoring/anthropic.py '    return AsyncAnthropic(api_key=key, base_url=API)' '    return AsyncAnthropic(api_key=key)' tests/test_anthropic_provider.py tests/test_authoring.py tests/test_advisor.py
$M auth16_refusal_answer src/ventoux/authoring/anthropic.py '        if response.stop_reason == "refusal":' '        if False:' tests/test_anthropic_provider.py tests/test_authoring.py tests/test_advisor.py
$M auth17_cut_short src/ventoux/authoring/anthropic.py '        if response.stop_reason not in WHOLE:' '        if False:' tests/test_anthropic_provider.py tests/test_authoring.py tests/test_advisor.py
$M auth18_empty_text src/ventoux/authoring/anthropic.py '        if not text:
            raise ProviderFailed' '        if False:
            raise ProviderFailed' tests/test_anthropic_provider.py tests/test_authoring.py tests/test_advisor.py
$M auth19_api_error_quoted src/ventoux/authoring/anthropic.py 'raise ProviderFailed(f"the model'"'"'s API failed: {type(error).__name__}") from None' 'raise ProviderFailed(f"the model'"'"'s API failed: {error}") from None' tests/test_anthropic_provider.py tests/test_authoring.py tests/test_advisor.py
$M auth20_replay_differs src/ventoux/authoring/provider.py '        if recorded.request is not None and (where := difference(recorded.request, request)):' '        if False and (where := difference(recorded.request, request)):' tests/test_advisor.py tests/test_temporal_advisor.py tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py
$M auth21_replay_system src/ventoux/authoring/provider.py '    if asked.system != recorded.system:' '    if False:' tests/test_advisor.py tests/test_temporal_advisor.py tests/test_authoring.py tests/test_drafting.py tests/test_approve.py tests/test_draft_sheet.py
$M auth22_advisor_admission src/ventoux/authoring/advisor.py '    if (why := await refused(step)) is not None:' '    if False:' tests/test_advisor.py tests/test_temporal_advisor.py
$M auth23_advisor_second_key src/ventoux/authoring/advisor.py '    if list(read) != ["step"]:' '    if False:' tests/test_advisor.py tests/test_temporal_advisor.py
$M auth24_advisor_name_strict src/ventoux/authoring/advisor.py '        return NAME.validate_python(step, strict=True)' '        return str(step)' tests/test_advisor.py tests/test_temporal_advisor.py
$M auth25_approve_errors src/ventoux/authoring/approve.py '    if errors:
        refused =' '    if False:
        refused =' tests/test_approve.py tests/test_draft_sheet.py
$M case01_untrusted_removes_approval src/ventoux/case/approvals.py '    for field, untrusted in untrusted_of(read).items():
        return (' '    for field, untrusted in {}.items():
        return (' $QUICK
$M case02_approval_not_withdrawn_on_change src/ventoux/case/approvals.py '        reason = not_admitted(case, required[name], state) or changed(approval, step, state)' '        reason = not_admitted(case, required[name], state)' $QUICK
$M case03_given_not_lapsed src/ventoux/case/approvals.py '        if different := changed_fields(given, step, state):' '        if different := []:' $QUICK
$M case04_case_lapsed_digest src/ventoux/case/approvals.py '    if now != given.digest:' '    if False:' $QUICK
$M case05_approval_outcome_open src/ventoux/case/answers.py '    if answer.outcome not in (APPROVE, REJECT):' '    if False:' $QUICK
$M case06_approval_risk src/ventoux/case/answers.py '    if approver is None:
        raise AnswerRefused(risk_refusal' '    if False:
        raise AnswerRefused(risk_refusal' $QUICK
$M case07_unseen_approves src/ventoux/case/answers.py '    refuse_unless(unseen(case, catalog, answer, name, step))' '    pass' $QUICK
$M case08_same_person_twice src/ventoux/case/answers.py '    if answer.by in approved:' '    if False:' $QUICK
$M case09_opener_approves src/ventoux/case/answers.py '    if by == state.opened_by:
        return f"{by} opened the case, so cannot approve its steps"' '    if False:
        return f"{by} opened the case, so cannot approve its steps"' $QUICK
$M case10_parent_excluded_ignored src/ventoux/case/answers.py '    if by in state.excluded:' '    if False:' $QUICK
$M case11_proposer_approves src/ventoux/case/answers.py '    if by == state.proposers.get(name):' '    if False:' $QUICK
$M case12_rule_reader_approves src/ventoux/case/answers.py '    if asked is not None and by in asked.read_from:' '    if False:' $QUICK
$M case13_retry_exclusion_dropped src/ventoux/case/answers.py '    if latest is not None and latest.status == "retrying" and by in latest.excluded:' '    if False:' $QUICK
$M case14_claim_held_by_other src/ventoux/case/claims.py '    if holder is not None:
        raise ClaimRefused(' '    if False:
        raise ClaimRefused(' $QUICK
$M case15_multi_approval_held src/ventoux/case/claims.py '    if isinstance(found, OpenApproval) and found.count > 1:' '    if False:' $QUICK
$M case16_give_back_by_other src/ventoux/case/claims.py '    if holder.by != event.by:' '    if False:' $QUICK
$M case17_answer_held_by_other src/ventoux/case/claims.py '    if holder is None or holder.by == by:
        return None' '    if True:
        return None' $QUICK
$M case18_assigner_role src/ventoux/case/assigning.py '    if role is None:
        allowed = " or ".join(catalog.assigners)' '    if False:
        allowed = " or ".join(catalog.assigners)' $QUICK
$M case19_own_judge src/ventoux/case/assigning.py '    if (why := why_excluded(case, state, found.step, step, by)) is not None:' '    if False:' $QUICK
$M case20_assignee_not_judged src/ventoux/case/assigning.py '        role_to_hold(case, catalog, state, found, asked)
' '        pass
' $QUICK
$M case21_sender_system src/ventoux/case/runtime.py '        if event.by != f"system:{sent_by.system}":' '        if False:' $QUICK
$M case22_people_event_from_system src/ventoux/case/runtime.py '    if event.by.startswith("system:"):
        raise EventRefused' '    if False:
        raise EventRefused' $QUICK
$M case23_sender_role src/ventoux/case/runtime.py '        raise EventRefused(f"{name} is sent by {roles}, and {event.by} has {known}")' '        pass' $QUICK
$M case24_event_after_close src/ventoux/case/runtime.py '    if state.phase == "closed":
        raise EventRefused' '    if False:
        raise EventRefused' $QUICK
$M case25_duplicate_item_keys src/ventoux/case/runtime.py '    if len(set(keys)) < len(keys):' '    if False:' $QUICK
$M case26_repeated_high_risk src/ventoux/case/runtime.py '    if contract.risk == "high":
        raise StepStopped(f"{contract.reference} is high risk, and {name} is repeated")' '    if False:
        raise StepStopped(f"{contract.reference} is high risk, and {name} is repeated")' $QUICK
$M case26_repeated_high_risk@REST src/ventoux/case/runtime.py '    if contract.risk == "high":
        raise StepStopped(f"{contract.reference} is high risk, and {name} is repeated")' '    if False:
        raise StepStopped(f"{contract.reference} is high risk, and {name} is repeated")' $REST
$M case26_repeated_high_risk@TEMP src/ventoux/case/runtime.py '    if contract.risk == "high":
        raise StepStopped(f"{contract.reference} is high risk, and {name} is repeated")' '    if False:
        raise StepStopped(f"{contract.reference} is high risk, and {name} is repeated")' $TEMP
$M case27_high_risk_no_approval src/ventoux/case/runtime.py '    if contract.risk == "high" and step.approval is None:' '    if False:' $QUICK
$M case28_retry_not_failed src/ventoux/case/runtime.py '    if run is None or run.status != "failed":' '    if run is None:' $QUICK
$M case29_stale_unknown_age src/ventoux/case/runtime.py '        if stale.age is None:  # fail closed: an age that can'"'"'t be told is never fresh
            raise StepStopped(f"{stale.field} has no time obtained, so {name} can'"'"'t tell its age")
        said =' '        if False:  # fail closed: an age that can'"'"'t be told is never fresh
            raise StepStopped(f"{stale.field} has no time obtained, so {name} can'"'"'t tell its age")
        said =' $QUICK
$M case30_max_age_ge src/ventoux/case/freshness.py '        elif at - obtained.at > seconds_in(limit):' '        elif at - obtained.at >= seconds_in(limit):' $QUICK
$M case31_max_age_no_time src/ventoux/case/freshness.py '        if obtained is None:
            stale.append(' '        if False:
            stale.append(' $QUICK
$M case32_bool_time src/ventoux/case/freshness.py '    if isinstance(at, bool) or not isinstance(at, int):' '    if not isinstance(at, int):' $QUICK
$M case33_timer_wrong_time src/ventoux/case/timers.py '    if event.at != timer.due:' '    if False:' $QUICK
$M case34_timer_due_strict src/ventoux/case/timers.py '    due = [timer for timer in state.timers if timer.due <= at]' '    due = [timer for timer in state.timers if timer.due < at]' $QUICK
$M case35_timer_tie src/ventoux/case/timers.py '    first = min(due, key=lambda timer: timer.due)' '    first = min(reversed(due), key=lambda timer: timer.due)' $QUICK
$M case36_timers_failed_ends src/ventoux/case/timers.py '        if status in ("done", "rejected", "cancelled", "skipped"):' '        if status in ("done", "rejected", "cancelled", "skipped", "failed"):' $QUICK
$M case37_failed_run_stopped src/ventoux/case/stopping.py '    if latest is not None and latest.status in ("failed", "retrying"):
        # Nothing' '    if False:
        # Nothing' $QUICK
$M case38_close_over_failed src/ventoux/case/closing.py '    if any(run.status in ("failed", "retrying") for run in state.runs):' '    if False:' $QUICK
$M case39_close_over_failed_rule src/ventoux/case/closing.py '    if any(firing.status == "failed" for firing in state.firings):' '    if False:' $QUICK
$M case40_close_over_owed src/ventoux/case/closing.py '    if owed(case, state):
        return  # nor' '    if False:
        return  # nor' $QUICK
$M case41_closes_when_any src/ventoux/case/closing.py '    if all(milestone in state.milestones for milestone in case.closes_when):' '    if any(milestone in state.milestones for milestone in case.closes_when):' $QUICK
$M case41_closes_when_any@REST src/ventoux/case/closing.py '    if all(milestone in state.milestones for milestone in case.closes_when):' '    if any(milestone in state.milestones for milestone in case.closes_when):' $REST
$M case41_closes_when_any@TEMP src/ventoux/case/closing.py '    if all(milestone in state.milestones for milestone in case.closes_when):' '    if any(milestone in state.milestones for milestone in case.closes_when):' $TEMP
$M case42_close_role src/ventoux/case/closing.py '    if role is None:
        registered = sorted(r for r in event.roles if r in catalog.roles)' '    if False:
        registered = sorted(r for r in event.roles if r in catalog.roles)' $QUICK
$M case43_forget_never src/ventoux/case/forgetting.py '    if family_forgetting(case, children) == "never":' '    if False:' $QUICK
$M case44_forget_family_ignores_children src/ventoux/case/forgetting.py '    said = [case.forgetting, *(child.forgetting for child in children)]' '    said = [case.forgetting]' $QUICK
$M case44_forget_family_ignores_children@REST src/ventoux/case/forgetting.py '    said = [case.forgetting, *(child.forgetting for child in children)]' '    said = [case.forgetting]' $REST
$M case44_forget_family_ignores_children@TEMP src/ventoux/case/forgetting.py '    said = [case.forgetting, *(child.forgetting for child in children)]' '    said = [case.forgetting]' $TEMP
$M case45_forget_self_approve src/ventoux/case/forgetting.py '    if approved_by == proposed_by:' '    if False:' $QUICK
$M case46_forget_opener_approves src/ventoux/case/forgetting.py '    if state.engine >= 2 and event.approved_by == state.opened_by:' '    if False:' $QUICK
$M case47_forget_proposer_role src/ventoux/case/forgetting.py '    if proposed is not None:
        raise ForgetRefused(proposed)' '    if False:
        raise ForgetRefused(proposed)' $QUICK
$M case48_change_self_approve src/ventoux/case/requests.py '    if by == request.by:' '    if False:' $QUICK
$M case49_change_opener_approves src/ventoux/case/requests.py '    if by == state.opened_by:
        return f"{by} opened the case, so cannot approve a change to it"' '    if False:
        return f"{by} opened the case, so cannot approve a change to it"' $QUICK
$M case50_edit_setter_approves src/ventoux/case/requests.py '    if f"person:{by}" in state.sources.get(request.target, ()):' '    if False:' $QUICK
$M case51_edit_hidden_approves src/ventoux/case/requests.py '    if (hidden := unseen(case, catalog, request.target, by, event.roles)) is not None:
        return hidden' '    if False:
        return hidden' $QUICK
$M case52_skip_approver_approves src/ventoux/case/requests.py '    if run.approved is not None and by in run.approved.approvers:' '    if False:' $QUICK
$M case53_edit_recheck_changed src/ventoux/case/requests.py '    if problem is None and inputs_digest({name: Var(var=name)}, state.values) != request.against:' '    if False:' $QUICK
$M case54_migrate_recheck_moved src/ventoux/case/requests.py '    if released(case, state) != request.against:' '    if False:' $QUICK
$M case55_change_kind_unknown src/ventoux/case/requests.py '    if event.kind not in KINDS:' '    if False:' $QUICK
$M case56_edit_sensitive_unwrapped src/ventoux/case/requests.py '    if declared.sensitive and not isinstance(value, Sensitive):' '    if False:' $QUICK
$M case57_edit_same_value src/ventoux/case/requests.py '    if plain(value) == plain(state.values[name]):' '    if False:' $QUICK
$M case58_skip_required src/ventoux/case/requests.py '    if case.steps[run.step].required:' '    if False:' $QUICK
$M case59_mig_unknown_engine src/ventoux/case/migrations.py '    if migration.engine not in KNOWN:' '    if False:' $QUICK
$M case60_mig_engine_back src/ventoux/case/migrations.py '    elif migration.engine < state.engine:' '    elif False:' $QUICK
$M case61_mig_type_change src/ventoux/case/migrations.py '        if before.declared != after.declared:' '        if False:' $QUICK
$M case62_mig_loses_sensitive src/ventoux/case/migrations.py '        if before.sensitive and not after.sensitive:' '        if False:' $QUICK
$M case63_mig_widens_visible src/ventoux/case/migrations.py '        if widened(case, target, name, new):' '        if False:' $QUICK
$M case64_mig_unknown_section src/ventoux/case/migrations.py '        if section not in SECTIONS:' '        if False:' $QUICK
$M case65_mig_two_to_one src/ventoux/case/migrations.py '            if new in mapped_to:' '            if False:' $QUICK
$M case66_mig_approval_kept src/ventoux/case/migrations.py '        if not same_behaviour(case, target, name):
            withdraw(' '        if False:
            withdraw(' $QUICK
$M case67_view_unregistered_role src/ventoux/case/visibility.py '    counting = {role for role in roles if role in registered}' '    counting = set(roles)' $QUICK
$M case68_child_has_cases src/ventoux/case/releases.py '        if child.cases:
' '        if False:
' $QUICK
$M case69_digest_method src/ventoux/case/releases.py '    if given.method != METHOD:
        return False' '    if False:
        return False' $QUICK
$M case70_record_digest_recheck src/ventoux/case/releases.py '    if digest(kept) != record.digest:' '    if False:' $QUICK
$M case71_reword_older_release src/ventoux/case/releases.py '        if number != newest:' '        if False:' $QUICK
$M case72_digest_default_kept src/ventoux/case/releases.py '    if at_default and not names_its_shape:' '    if False:' $QUICK
$M case73_digest_wording_kept src/ventoux/case/releases.py '    if isinstance(value, WORDING):
        return ABSENT' '    if False:
        return ABSENT' $QUICK
$M case74_act_no_poller src/ventoux/case/activation.py '    if not pollers.get(queue):
        # A manifest' '    if False:
        # A manifest' $QUICK
$M case75_act_unmanifested_poller src/ventoux/case/activation.py '        if manifest is None or (manifest.environment, manifest.task_queue) != here:' '        if manifest is None:' $QUICK
$M case76_act_hash src/ventoux/case/activation.py '    if served != needed:' '    if False:' $QUICK
$M case77_act_bind_differently src/ventoux/case/activation.py '    if len(set(bindings.values())) > 1:' '    if False:' $QUICK
$M case78_required_with_when src/ventoux/case/definition.py '    if step.required and step.when is not None:' '    if False:' $QUICK
$M case79_report_sensitive src/ventoux/case/definition.py '        elif field.sensitive:
            problems.append(' '        elif False:
            problems.append(' $QUICK
$M case80_sensitive_to_child src/ventoux/case/calls.py '                if read in case.fields and case.fields[read].sensitive:' '                if False:' $QUICK
$M core01_risk_not_checked_for_approver src/ventoux/core/approval.py '        and may_approve(catalog.roles[role], contract.risk)
' '        and True
' $QUICK
$M core02_approver_role_not_listed src/ventoux/core/approval.py '        if role in roles
' '        if True
' $QUICK
$M core02_approver_role_not_listed@FAST src/ventoux/core/approval.py '        if role in roles
' '        if True
' $FAST
$M core02_approver_role_not_listed@TEMP src/ventoux/core/approval.py '        if role in roles
' '        if True
' $TEMP
$M core03_own_answer_approves src/ventoux/core/approval.py 'if f"person:{person}" in sources.get(field, frozenset()):' 'if False:' $QUICK
$M core04_conditions_not_someone_else src/ventoux/core/approval.py '((inputs, f"{step} uses"), (conditions, f"decides whether {step} runs"))' '((inputs, f"{step} uses"),)' $QUICK
$M core05_digest_of_sensitive_plain src/ventoux/core/approval.py 'return Sensitive(digest) if read else digest' 'return digest' $QUICK
$M core06_digest_number_as_text src/ventoux/core/approval.py 'default=lambda number: {"number": str(number)}' default=str $QUICK
$M core06_digest_number_as_text@FAST src/ventoux/core/approval.py 'default=lambda number: {"number": str(number)}' default=str $FAST
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
$M core22_infinite_number_fits@FAST src/ventoux/core/form.py 'return isinstance(value, Decimal) and value.is_finite()' 'return isinstance(value, Decimal)' $FAST
$M core23_empty_option_fits src/ventoux/core/form.py 'return isinstance(value, str) and value != ""' 'return isinstance(value, str)' $QUICK
$M core23_empty_option_fits@FAST src/ventoux/core/form.py 'return isinstance(value, str) and value != ""' 'return isinstance(value, str)' $FAST
$M core24_empty_attachment_fits src/ventoux/core/form.py '0 < len(value) <= LONGEST_ID' '0 <= len(value) <= LONGEST_ID' $QUICK
$M core24_empty_attachment_fits@FAST src/ventoux/core/form.py '0 < len(value) <= LONGEST_ID' '0 <= len(value) <= LONGEST_ID' $FAST
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
$M core35_moment_read@FAST src/ventoux/core/expressions/evaluate.py '    if isinstance(expression, date) and not is_day(expression):' '    if False:' $FAST
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
$M caseR01_migration_label_mismatch src/ventoux/case/requests.py '        if not isinstance(migration, Migration) or migration.label != event.target:' '        if not isinstance(migration, Migration):' $QUICK
$M caseR01_migration_label_mismatch@REST src/ventoux/case/requests.py '        if not isinstance(migration, Migration) or migration.label != event.target:' '        if not isinstance(migration, Migration):' $REST
$M caseR02_shown_unset src/ventoux/case/runtime.py '    if event.field not in state.values:
        raise ShownRefused' '    if False:
        raise ShownRefused' $QUICK
$M caseR02_shown_unset@REST src/ventoux/case/runtime.py '    if event.field not in state.values:
        raise ShownRefused' '    if False:
        raise ShownRefused' $REST
$M caseR03_notes_no_record_before src/ventoux/case/notes.py '    if not found:
        raise NotesRefused' '    if False:
        raise NotesRefused' $QUICK
$M caseR03_notes_no_record_before@REST src/ventoux/case/notes.py '    if not found:
        raise NotesRefused' '    if False:
        raise NotesRefused' $REST
$M caseR04_notes_contract_missing src/ventoux/case/notes.py '        except NotInCatalog:
            raise NotesRefused(' '        except NotInCatalog:
            continue
            raise NotesRefused(' $QUICK
$M caseR04_notes_contract_missing@REST src/ventoux/case/notes.py '        except NotInCatalog:
            raise NotesRefused(' '        except NotInCatalog:
            continue
            raise NotesRefused(' $REST
$M caseR05_notes_wording_diff src/ventoux/case/notes.py '    if kept.wording > 1 and (found.changes or found.rewritten):' '    if False:' $QUICK
$M caseR06_reading_unknown_type src/ventoux/case/reading.py '    if kind not in kinds:
        raise ReadingRefused' '    if False:
        raise ReadingRefused' $QUICK
$M caseR06_reading_unknown_type@REST src/ventoux/case/reading.py '    if kind not in kinds:
        raise ReadingRefused' '    if False:
        raise ReadingRefused' $REST
$M caseR07_reading_unknown_state src/ventoux/case/reading.py '        raise ReadingRefused(f"can'"'"'t read {name}: {state!r} is no kind of state")' '        return f"{name}."' $QUICK
$M caseR07_reading_unknown_state@REST src/ventoux/case/reading.py '        raise ReadingRefused(f"can'"'"'t read {name}: {state!r} is no kind of state")' '        return f"{name}."' $REST
$M caseR08_plain_unknown_reading src/ventoux/case/plain.py '    raise TypeError(f"no reading of the kind {type(reading).__name__}")  # fail closed' '    return "", ()  # fail closed' $QUICK
$M caseR08_plain_unknown_reading@REST src/ventoux/case/plain.py '    raise TypeError(f"no reading of the kind {type(reading).__name__}")  # fail closed' '    return "", ()  # fail closed' $REST
$M caseR09_digest_unknown_value src/ventoux/case/releases.py '    raise TypeError(f"the behaviour digest can'"'"'t read a {type(value).__name__}")' '    return None' $QUICK
$M caseR09_digest_unknown_value@REST src/ventoux/case/releases.py '    raise TypeError(f"the behaviour digest can'"'"'t read a {type(value).__name__}")' '    return None' $REST
$M caseR10_record_other_package src/ventoux/case/releases.py '    if record.name != name:
        raise RecordRefused' '    if False:
        raise RecordRefused' $QUICK
$M caseR10_record_other_package@REST src/ventoux/case/releases.py '    if record.name != name:
        raise RecordRefused' '    if False:
        raise RecordRefused' $REST
$M caseR11_diff_unknown_value src/ventoux/case/changes.py '    raise DiffRefused(f"the diff can'"'"'t show a {type(value).__name__}")' '    return ""' $QUICK
$M caseR11_diff_unknown_value@REST src/ventoux/case/changes.py '    raise DiffRefused(f"the diff can'"'"'t show a {type(value).__name__}")' '    return ""' $REST
$M caseR12_event_two_senders src/ventoux/case/definition.py '        if (self.system is None) == (self.roles is None):' '        if False:' $QUICK
$M caseR13_assign_answered_no_step src/ventoux/case/definition.py '        if self.to == "answered" and self.step is None:' '        if False:' $QUICK
$M caseR14_reminder_no_age src/ventoux/case/definition.py '    if not ages:
        raise ValueError('"'"'a reminder' '    if False:
        raise ValueError('"'"'a reminder' $QUICK
$M caseR15_story_answer_names_one src/ventoux/case/story.py '        if (self.step is None) == (self.entry is None):' '        if False:' $QUICK
$M caseR15_story_answer_names_one@REST src/ventoux/case/story.py '        if (self.step is None) == (self.entry is None):' '        if False:' $REST
$M coreR01_promise_key_not_text src/ventoux/core/promise.py '            if not isinstance(key, str):
                raise PromiseUnreadable' '            if False:
                raise PromiseUnreadable' $QUICK
$M coreR01_promise_key_not_text@REST src/ventoux/core/promise.py '            if not isinstance(key, str):
                raise PromiseUnreadable' '            if False:
                raise PromiseUnreadable' $REST
$M coreR02_schema_model_config src/ventoux/core/contract_schema.py '    if model.model_config:' '    if False:' $QUICK
$M coreR03_schema_default src/ventoux/core/contract_schema.py '    if not field.is_required() and field.default is not None:' '    if False:' $QUICK
$M coreR04_schema_unknown_mark src/ventoux/core/contract_schema.py '    if any(not isinstance(mark, MARKS) for mark in field.metadata):' '    if False:' $QUICK
$M coreR05_plan_no_roles src/ventoux/core/plan.py '    if not roles:
        raise ValueError("a wait or an approval' '    if False:
        raise ValueError("a wait or an approval' $QUICK
$M coreR06_plan_source_label src/ventoux/core/plan.py '    if f"{origin}:" != UNTRUSTED_ORIGIN or not is_label(label):' '    if False:' $QUICK
$M coreR07_only_from_no_system src/ventoux/core/policy.py '        if not self.systems:' '        if False:' $QUICK
$M coreR08_idempotency_required src/ventoux/core/contract.py '        if self.effect in ("write", "notify") and self.idempotency_key is None:' '        if False:' $QUICK
$M coreR09_output_label_unregistered src/ventoux/core/catalog.py '            if origin == "untrusted" and label not in self._labels:' '            if False:' $QUICK
$M coreR10_output_system_unregistered src/ventoux/core/catalog.py '            if origin == "system" and label not in self._systems:' '            if False:' $QUICK
$M coreR11_item_outside src/ventoux/core/expressions/evaluate.py '        if element is None:
' '        if False:
' $QUICK
$M coreR11_item_outside@REST src/ventoux/core/expressions/evaluate.py '        if element is None:
' '        if False:
' $REST
$M temp01_codec_no_case src/ventoux/temporal/codec.py '        if self.case is None:
            # Fail closed: never written' '        if False:
            # Fail closed: never written' tests/test_temporal_sensitive.py tests/test_sensitive.py
$M temp02_codec_skips_parts src/ventoux/temporal/codec.py 'names = sorted(name for name in payload.metadata if name.startswith(before))' 'names = []' tests/test_temporal_sensitive.py tests/test_sensitive.py
$M temp03_failure_not_sealed src/ventoux/temporal/codec.py '            "message": Sensitive(failure.message),' '            "message": failure.message,' tests/test_temporal_sensitive.py tests/test_sensitive.py
$M temp04_failure_message_kept src/ventoux/temporal/codec.py 'failure.message, failure.stack_trace = ENCODED_FAILURE, ""' 'failure.stack_trace = ""' tests/test_temporal_sensitive.py tests/test_sensitive.py
$M temp05_log_keeps_exception src/ventoux/temporal/logs.py '        record.exc_info, record.exc_text, record.stack_info = None, None, None' '        pass' tests/test_temporal_sensitive.py tests/test_sensitive.py
$M temp06_log_filter_not_installed src/ventoux/temporal/logs.py '            logger.addFilter(TYPE_ONLY)' '            pass' tests/test_temporal_sensitive.py tests/test_sensitive.py
$M temp07_converter_reads_encrypted src/ventoux/temporal/converter.py '        if any(name.startswith(ENCRYPTED) for name in payload.metadata):' '        if False:' tests/test_temporal_sensitive.py tests/test_sensitive.py
$M temp08_client_without_codec src/ventoux/temporal/converter.py '    if not isinstance(converter.payload_codec, SensitiveCodec) or (' '    if False and (' tests/test_temporal_sensitive.py tests/test_sensitive.py tests/test_temporal.py
$M temp09_converter_float src/ventoux/temporal/converter.py '    if isinstance(value, float):' '    if False:' tests/test_temporal_sensitive.py tests/test_sensitive.py tests/test_temporal.py tests/test_expressions.py
$M temp10_converter_mark_key src/ventoux/temporal/converter.py '        if MARK in value:' '        if False:' tests/test_temporal_sensitive.py tests/test_sensitive.py tests/test_temporal.py
$M temp11_export_in_clear src/ventoux/temporal/audit.py '        if field in sensitive and not isinstance(value, Sensitive):' '        if False:' tests/test_audit_export.py tests/test_audit_records.py
$M temp12_export_restricted_unsaid src/ventoux/temporal/audit.py '            if field in self.restricted:' '            if False:' tests/test_audit_export.py tests/test_audit_records.py
$M temp13_export_retries_11 src/ventoux/temporal/cases.py '    maximum_attempts=10,' '    maximum_attempts=11,' tests/test_audit_export.py tests/test_audit_records.py
$M temp14_export_refused_retried src/ventoux/temporal/cases.py '    non_retryable_error_types=["ExportRefused", "AuditRefused", "KeyRefused"],' '    non_retryable_error_types=["AuditRefused", "KeyRefused"],' tests/test_audit_export.py tests/test_audit_records.py
$M temp15_audit_bound_257 src/ventoux/temporal/cases.py '    audit_bound: ClassVar[int] = 256 * 1024' '    audit_bound: ClassVar[int] = 257 * 1024' tests/test_audit_export.py tests/test_audit_records.py
$M temp16_hold_strict src/ventoux/temporal/cases.py '        return waiting_size(self.state.audit) >= self.audit_bound' '        return waiting_size(self.state.audit) > self.audit_bound' tests/test_audit_export.py tests/test_audit_records.py
$M temp17_opens_unreleased src/ventoux/temporal/cases.py '        if not is_release(case, release.plans, release.digest, release.cases):' '        if False:' tests/test_temporal_case_release.py tests/test_temporal_children.py
$M temp18_wording_unchecked src/ventoux/temporal/cases.py '        if not is_release(case, plans, self.release.digest):
            raise refused' '        if False:
            raise refused' tests/test_temporal_case_release.py tests/test_notes.py tests/test_releases.py
$M temp19_engine_not_opening src/ventoux/temporal/cases.py '    if event.value.engine in KNOWN and event.value.engine not in OPENING:' '    if False:' tests/test_temporal_migrations.py tests/test_migrations.py
$M temp20_forget_child_alone src/ventoux/temporal/forget.py '    if "/" not in case:
        return None' '    if True:
        return None' tests/test_forget.py tests/test_temporal_forget.py
$M temp20_forget_child_alone@TEMP src/ventoux/temporal/forget.py '    if "/" not in case:
        return None' '    if True:
        return None' $TEMP
$M temp21_forget_unreadable_definition src/ventoux/temporal/forget.py '    if found.forgetting == "":' '    if False:' tests/test_forget.py tests/test_temporal_forget.py
$M temp22_forget_while_open_closed src/ventoux/temporal/forget.py '    if found.forgetting == "while_open" and not found.running:' '    if False:' tests/test_forget.py tests/test_temporal_forget.py
$M temp23_forget_never src/ventoux/temporal/forget.py '    if found.forgetting == "never":
        return' '    if False:
        return' tests/test_forget.py tests/test_temporal_forget.py
$M temp24_forget_same_person src/ventoux/temporal/forget.py '    if by == found.by:' '    if False:' tests/test_forget.py tests/test_temporal_forget.py
$M temp25_closed_first_ignored src/ventoux/temporal/forget.py '            if self.found.forgetting == "while_open":' '            if False:' tests/test_forget.py tests/test_temporal_forget.py
$M temp26_forget_identifier src/ventoux/temporal/forget.py '        if (wrong := identifier_problem(sent.by)) is not None:' '        if False:' tests/test_forget.py tests/test_temporal_forget.py
$M temp27_contract_check_new_work src/ventoux/temporal/contract_check.py '        if event.event_id > asked and (what := new_work(event)) is not None:' '        if False:' tests/test_temporal_workflow_step.py tests/test_workflow_step.py tests/test_temporal_keys.py
$M temp28_contract_check_ends_early src/ventoux/temporal/contract_check.py '    if started:
        problems.append' '    if False:
        problems.append' tests/test_temporal_workflow_step.py tests/test_workflow_step.py tests/test_temporal_keys.py
$M temp29_contract_check_undeclared_output src/ventoux/temporal/contract_check.py '        if name not in contract.output.model_fields
' '        if False
' tests/test_temporal_workflow_step.py tests/test_workflow_step.py tests/test_temporal_keys.py
$M temp30_manifest_refused src/ventoux/temporal/registry.py '    if not answer.done:
        raise ManifestRefused' '    if False:
        raise ManifestRefused' tests/test_temporal_registry.py tests/test_temporal_activate.py
$M temp31_carried_bool_number src/ventoux/temporal/carried.py '    if isinstance(number, bool) or not isinstance(number, int | Decimal) or number % 1 != 0:' '    if not isinstance(number, int | Decimal) or number % 1 != 0:' tests/test_temporal_case.py tests/test_repeated.py tests/test_required.py
$M temp32_carried_bad_date src/ventoux/temporal/carried.py '    if day is None:
        raise ValueError' '    if False:
        raise ValueError' tests/test_temporal_dates.py tests/test_dates.py tests/test_temporal_case.py
$M tool01_vault_exportable src/ventoux/tooling/vault.py '        if config[setting] is not False:' '        if False:' tests/test_vault_keys.py tests/test_doctor.py
$M tool02_vault_type src/ventoux/tooling/vault.py '    if config["type"] != KEY_TYPE:' '    if False:' tests/test_vault_keys.py tests/test_doctor.py
$M tool03_vault_http src/ventoux/tooling/vault.py '    if parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in LOCAL):' '    if True:' tests/test_vault_keys.py tests/test_doctor.py
$M tool04_vault_proxy src/ventoux/tooling/vault.py 'urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())' 'urllib.request.build_opener(NoRedirect())' tests/test_vault_keys.py tests/test_doctor.py
$M tool05_vault_redirect src/ventoux/tooling/vault.py 'urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())' 'urllib.request.build_opener(urllib.request.ProxyHandler({}))' tests/test_vault_keys.py tests/test_doctor.py
$M tool06_vault_mark_ignored_use src/ventoux/tooling/vault.py '        if self.marked(case, name):
            raise KeyRefused(' '        if False:
            raise KeyRefused(' tests/test_vault_keys.py tests/test_doctor.py
$M tool07_vault_state_mark src/ventoux/tooling/vault.py '        if self.marked(case, name):
            return "destroyed"' '        if False:
            return "destroyed"' tests/test_vault_keys.py tests/test_doctor.py
$M tool08_vault_destroy_no_mark src/ventoux/tooling/vault.py '            self.ask(case, "POST", self.mark_path(name), mark, {200, 204})' '            pass' tests/test_vault_keys.py tests/test_doctor.py
$M tool09_vault_destroy_none src/ventoux/tooling/vault.py '            if self.key_config(case, name) is None:
                # Fail closed' '            if False:
                # Fail closed' tests/test_vault_keys.py tests/test_doctor.py
$M tool10_vault_name_long src/ventoux/tooling/vault.py '    if len(name) > LONGEST:' '    if False:' tests/test_vault_keys.py tests/test_doctor.py
$M tool11_vault_token_unset src/ventoux/tooling/vault.py '        if not token:
            raise KeyUnavailable(NO_TOKEN)' '        if False:
            raise KeyUnavailable(NO_TOKEN)' tests/test_vault_keys.py tests/test_doctor.py
$M tool11_vault_token_unset@FAST src/ventoux/tooling/vault.py '        if not token:
            raise KeyUnavailable(NO_TOKEN)' '        if False:
            raise KeyUnavailable(NO_TOKEN)' $FAST
$M tool12_filekeys_reuse src/ventoux/tooling/keys.py '        if case in keys:
            raise KeyRefused(f"a key was already made' '        if False:
            raise KeyRefused(f"a key was already made' tests/test_vault_keys.py tests/test_temporal_keys.py tests/test_forget.py
$M tool13_filekeys_destroyed_used src/ventoux/tooling/keys.py '        if stored is DESTROYED:' '        if False:' tests/test_vault_keys.py tests/test_temporal_keys.py tests/test_forget.py tests/test_temporal_sensitive.py
$M tool14_filekeys_damaged src/ventoux/tooling/keys.py '        except InvalidTag:
            # Fail closed: never a guess at what it held.
' '        except InvalidTag:
            return b'"'"'null'"'"'
' tests/test_vault_keys.py tests/test_temporal_sensitive.py tests/test_sensitive.py
$M tool15_doctor_dev_provider src/ventoux/tooling/doctor.py '        if development is True:' '        if False:' tests/test_doctor.py tests/test_doctor_live.py tests/test_connecting.py
$M tool16_doctor_unsaid_provider src/ventoux/tooling/doctor.py '        if development is not False:' '        if False:' tests/test_doctor.py tests/test_doctor_live.py tests/test_connecting.py
$M tool17_doctor_dev_catalog src/ventoux/tooling/doctor.py '    if name == DEVELOPMENT:' '    if False:' tests/test_doctor.py tests/test_doctor_live.py tests/test_connecting.py
$M tool18_doctor_dev_env src/ventoux/tooling/doctor.py '    if registry.development:
        return "FAILED"' '    if False:
        return "FAILED"' tests/test_doctor.py tests/test_doctor_live.py tests/test_connecting.py
$M tool19_doctor_outside_deny src/ventoux/tooling/doctor.py '    if held[outside] != ["deny"]:' '    if False:' tests/test_doctor.py tests/test_doctor_live.py tests/test_connecting.py
$M tool20_doctor_mark_delete src/ventoux/tooling/doctor.py '        if {"delete", "root"} & set(held[path])' '        if False' tests/test_doctor.py tests/test_doctor_live.py tests/test_connecting.py
$M tool21_doctor_bound src/ventoux/tooling/doctor.py 'PROBE_BOUND = 10.0  # seconds' 'PROBE_BOUND = 11.0  # seconds' tests/test_doctor.py tests/test_doctor_live.py tests/test_connecting.py
$M tool21_doctor_bound@FAST src/ventoux/tooling/doctor.py 'PROBE_BOUND = 10.0  # seconds' 'PROBE_BOUND = 11.0  # seconds' $FAST
$M tool22_keeping_dev_keys src/ventoux/case/registry.py '    elif manifest.keys.development:' '    elif False:' tests/test_doctor.py tests/test_doctor_live.py tests/test_connecting.py tests/test_temporal_registry.py tests/test_activation.py
$M tool23_deploy_no_catalog src/ventoux/tooling/deployment.py '    if name is None:
        raise Unconfigured(
            "no catalog is named' '    if False:
        raise Unconfigured(
            "no catalog is named' tests/test_deployment_catalog.py tests/test_check.py tests/test_cli.py tests/test_diff.py
$M tool24_connect_identity src/ventoux/tooling/connecting.py '    if identity is None or identity not in temporal.identities:' '    if False:' tests/test_doctor.py tests/test_doctor_live.py tests/test_connecting.py
$M tool25_sheet_not_drafted src/ventoux/tooling/draft_sheet.py '    if record.verdict != "drafted":' '    if False:' tests/test_drafting.py tests/test_draft_sheet.py tests/test_approve.py tests/test_authoring.py
$M tool26_sheet_hash src/ventoux/tooling/draft_sheet.py '    if hashlib.sha256(written).hexdigest() != record.draft_sha256:' '    if False:' tests/test_drafting.py tests/test_draft_sheet.py tests/test_approve.py tests/test_authoring.py
$M tool27_sheet_reference src/ventoux/tooling/draft_sheet.py '    if (reference := reference_of(text)) != record.plan:' '    if False:' tests/test_drafting.py tests/test_draft_sheet.py tests/test_approve.py tests/test_authoring.py
$M tool28_sheet_package src/ventoux/tooling/draft_sheet.py '    if before.name != record.package:' '    if False:' tests/test_drafting.py tests/test_draft_sheet.py tests/test_approve.py tests/test_authoring.py
$M tool29_drafts_folder_default src/ventoux/tooling/drafting.py '    if found.drafts is None:' '    if False:' tests/test_drafting.py tests/test_draft_sheet.py tests/test_approve.py tests/test_authoring.py
$M tool30_abandoned_written src/ventoux/tooling/drafting.py '    if authored.verdict == "drafted" and authored.plan is not None:
        plan_file.write_text(authored.plan)' '    if True:
        plan_file.write_text(authored.plan or "")' tests/test_drafting.py tests/test_draft_sheet.py tests/test_approve.py tests/test_authoring.py
$M tool31_record_overwritten src/ventoux/tooling/releases.py '            raise RecordRefused(
                f"{path} already exists, with other content' '            return False
            raise RecordRefused(
                f"{path} already exists, with other content' tests/test_releases.py tests/test_summary.py tests/test_notes.py
$M tool32_record_without_notes src/ventoux/tooling/releases.py '        if kept.notes is None:' '        if False:' tests/test_releases.py tests/test_summary.py tests/test_notes.py
$M tool33_unchanged_bytes src/ventoux/tooling/check.py '        elif committed.read_bytes() != text.encode():' '        elif False:' tests/test_check.py tests/test_unchanged.py tests/test_cli.py
$M tool34_record_path_name src/ventoux/tooling/releases.py '            if path.name != file_name(kept):' '            if False:' tests/test_releases.py tests/test_summary.py tests/test_notes.py
$M coreU01_evaluator_unknown src/ventoux/core/expressions/evaluate.py '    raise ExpressionError(f"can'"'"'t evaluate {expression!r}: it isn'"'"'t a parsed expression")' '    return False' $QUICK
$M coreU02_type_check_unknown src/ventoux/core/expressions/check.py '    raise refused(path, f"can'"'"'t check {expression!r}")' '    return BooleanType()' $QUICK
$M coreU02_type_check_unknown@REST src/ventoux/core/expressions/check.py '    raise refused(path, f"can'"'"'t check {expression!r}")' '    return BooleanType()' $REST
$M coreU03_render_unknown src/ventoux/core/expressions/render.py '    raise ExpressionInvalid(f"can'"'"'t render {expression!r}: it isn'"'"'t a parsed expression")' '    return ""' $QUICK
$M coreU04_fields_read_unknown src/ventoux/core/provenance.py '    raise TypeError(f"not an expression: {type(expression).__name__}")' '    return []' $QUICK
$M coreU05_state_kind_unknown src/ventoux/core/interpreter.py '                raise Stop(f"{here} is a kind of state this engine doesn'"'"'t know: {kind}")' '                run.status = "succeeded"' $QUICK
$M caseU01_moment_unknown src/ventoux/case/rules.py '    raise ValueError(f"{moment!r} is not a moment Ventoux knows")' '    return "opened"  # type: ignore' $QUICK
