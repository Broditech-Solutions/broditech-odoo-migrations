# Studio view audit: Odoo 17 to Odoo 19

The supplied `4804197-upgraded/dump_17.sql` and `dump_19.sql` contain the same
116 Studio-owned views and 932 stored translated architectures: 37 list views,
17 forms, 3 searches, 4 pivots, 2 kanbans, and 53 QWeb templates. Three other
views initially matching “Studio” belong to standard `web_studio`, rather than
customer customizations.

The core upgrade converted tree views to lists and disabled 14 formerly
active Studio views. Seven views were already inactive in 17; they stay
inactive. Two active overlays depend on deliberately retired addons:
`crm_salesperson_planner` and `account_due_list`. They are archived/detached
before cleanup. A retired model's view may subsequently be removed by the
model uninstall itself; its migration snapshot survives.

## Repairs

- Contacts/CRM: remove retired commission, payment, and location references;
  use phone and `invoice_edi_format`; preserve custom event, classification,
  supplier evaluation, brand, photograph, and contact fields.
- CRM form: resolve all 104 ordered Studio operations against the 17 view,
  then replace positional XPath expressions with semantic targets. Preserve
  operation order and stop if the expected sequence has changed.
- Projects: use `name` and `account_id`, place the custom dashboard inside
  `button_box` after Dropbox removal, and retain budget, area, priority, design,
  event, and Avant customizations without the retired `project_type` move.
- Accounting: adapt invoice amount/status/sequence-gap anchors; remove retired
  payment/commission references; retain financing, project, employee, and
  estimated collection fields.
- Sales/purchases: adapt line tax fields and salesperson/team placement,
  remove obsolete reminder/filter controls, and preserve project/analytic
  fields and product creation restrictions.
- Budgets/timesheets/appraisals: use `budget_line_ids`, decimal `unit_amount`,
  and current appraisal fields while keeping bonus/evaluation customizations.
- Reports: preserve copied invoice/sales layouts and template keys, remove
  retired payment/mandate/packaging references, rename sale unit/tax fields,
  and display subsection lines as sections. Copied tax helpers delegate to
  Odoo 19's maintained templates with an explicit currency. The obsolete
  company-currency helper override becomes a no-op: its only customization
  over the old implementation was an empty paragraph.

Every changed view's full original row is stored in
`broditech_studio_view_backup`, including translations, activation, and
inheritance metadata. The first snapshot is immutable. Reruns respect views
subsequently disabled by the user and do not duplicate backups.

## Validation and limits

- 47 automated tests cover transformations, model-scoped field changes,
  translations, snapshots, sequence guards, orphan archival, repeat runs,
  and stopping cleanup if preservation fails.
- All 932 architectures parse. Active QWeb expressions pass Python syntax
  checks, and no unmatched conditional branches remain.
- Odoo's official XML inheritance helper replayed the available source views:
  2,175 current definitions, 105 applicable combined roots, and matching XPath
  skeletons for 199 translated inherited architectures. No missing form/list
  fields were found against the upgraded metadata.
- The actual dump's view/XML-ID/field metadata was applied in a SQLite SQL
  simulation: 51 original rows backed up, 14 reactivated, 2 overlays detached.
  A second run left the results and snapshots unchanged.
- Community source: `0f7a58f9d1db6633edf68c16b0df5c2baf45faef`.
  Enterprise source: `ab4b3270fef0a3c86e9b705f7c609aa7605686e4`.
  Custom-addon source: `59910718c095052a64629b138cdb2150d10c3bfa`.

These checks do **not** replace an Odoo/PostgreSQL registry load, access-rights
or JavaScript-widget testing, or PDF rendering. Source replay covers view
records in the supplied dump and does not simulate creation of new view records
by later addon loading. Open the main screens and print every custom invoice
and quotation variant on a fresh staging restore before production.
No business records, dumps, or complete architectures are committed here.

To reproduce the inventory and optional source-aware checks:

```sh
PYTHONPATH=src python3 tools/audit_studio_dumps.py \
  --before ../4804197-upgraded/dump_17.sql \
  --after ../4804197-upgraded/dump_19.sql \
  --odoo-source /path/to/odoo-19-source \
  --enterprise-addons ../docker/odoo/v19/enterprise \
  --custom-addons ../docker/odoo/v19/addons/sanz-manor-odoo \
  --output /tmp/studio-audit.json
```

Output contains only inventory and diagnostics. Source arguments are optional;
without them, the tool compares dumps and checks XML transformations.

## Complete inventory

“Adapt/check” includes compatible views left unchanged. “Reactivate” applies
only to the explicit restoration list. IDs provide dump traceability; production
uses XML IDs to identify specific customizations.

| Dump ID | Studio XML ID suffix | Model / kind | Action | Languages |
| --- | --- | --- | --- | --- |
| 3010 | `odoo_studio_account__b9fb7668-fb96-4638-bc73-5a86f780f9a6` | `account.asset` / list | Adapt/check | 1 |
| 3011 | `odoo_studio_account__b9cb3c79-a34f-48e8-86d9-ddc4662d004f` | `account.asset` / list | Adapt/check | 1 |
| 3012 | `odoo_studio_res_part_da91894a-c216-4ec2-92ed-54f88f567150` | `res.partner` / list | Adapt/check | 1 |
| 3013 | `odoo_studio_project__452d6f82-b09b-4f03-9abb-1914bdd6c250` | `project.project` / list | Reactivate + adapt | 1 |
| 3014 | `odoo_studio_account__ed669a58-cf01-4582-9842-64d4346f1ae4` | `account.analytic.account` / list | Adapt/check | 1 |
| 3195 | `odoo_studio_jobs_rec_539e0d99-533d-46eb-a87a-2bb25bf45d5f` | `hr.applicant` / form | Adapt/check | 1 |
| 3196 | `odoo_studio_product__3bc60e33-a081-4ca1-b466-cb314009ed7c` | `product.template` / list | Adapt/check | 1 |
| 3371 | `odoo_studio_account__cf402e76-b030-45d0-b922-6c81f1629883` | `account.move` / list | Reactivate + adapt | 1 |
| 3373 | `odoo_studio_server_a_ad496c7b-0366-492d-8fc9-e33ec1c5c9e5` | `ir.actions.server` / list | Adapt/check | 1 |
| 3374 | `odoo_studio_project__67261d93-36d8-41c8-8ab1-d8cfc1e23a5a` | `project.task` / list | Adapt/check | 1 |
| 3375 | `odoo_studio_project__bef12995-32d1-4ae4-b524-419be1194356` | `project.task` / form | Adapt/check | 1 |
| 3377 | `odoo_studio_crm_lead_3067f923-c98e-4f9a-8afc-070b39b06d18` | `crm.lead` / form | Reactivate + adapt | 2 |
| 3379 | `default_list_view_fo_c5e6626f-17ac-4545-ba81-8ca15d48a043` | `x_crm_lead_line_2c967` / list | Adapt/check | 1 |
| 3380 | `default_form_view_fo_fa5d1001-1d9a-4238-8362-483fc58b554e` | `x_crm_lead_line_2c967` / form | Adapt/check | 1 |
| 3381 | `default_search_view__df29d201-294b-47a2-8ebc-63070bd6af9c` | `x_crm_lead_line_2c967` / search | Adapt/check | 1 |
| 3398 | `odoo_studio_crm_sale_a705a763-0ba3-4bbe-a130-1d198d715b3b` | `crm.salesperson.planner.visit.template` / form | Archive | 2 |
| 3399 | `odoo_studio_crm_lead_2afa26eb-c7d0-45f6-a035-75a8c7cce195` | `crm.lead` / list | Reactivate + adapt | 1 |
| 3400 | `odoo_studio_ir_ui_vi_788270b3-e7d5-4ef8-bf9d-0e9c071ede8e` | `ir.ui.view` / list | Adapt/check | 1 |
| 3402 | `odoo_studio_project__88573a1f-c07b-45f4-becf-1dc7281754c4` | `project.project` / form | Adapt/check | 2 |
| 3403 | `odoo_studio_crm_lead_97d08ad1-87f5-4a18-9604-220223245e26` | `crm.lead` / list | Adapt/check | 1 |
| 3432 | `odoo_studio_purchase_a36171a2-b5eb-4d08-94e8-7449b1264c7c` | `purchase.order` / form | Reactivate + adapt | 1 |
| 3512 | `odoo_studio_project__44a4f923-fd39-41db-8657-7d95abf8b09d` | `project.project` / kanban | Adapt/check | 1 |
| 3594 | `default_pivot_view_f_ab6d6176-b312-4b2a-ae86-7ed5ad213f6b` | `project.project` / pivot | Adapt/check | 1 |
| 3595 | `odoo_studio_crossove_8dfd385a-9cb3-40eb-879f-49225bec3d3e` | `budget.analytic` / list | Reactivate + adapt | 1 |
| 3596 | `odoo_studio_calendar_edbbbb2a-fc62-42be-9ad1-1a5ccd67e831` | `calendar.event` / form | Adapt/check | 2 |
| 3597 | `odoo_studio_account__e081d8c7-9bcf-44ea-85a3-e61f1df9e97b` | `account.analytic.line` / list | Adapt/check | 1 |
| 3598 | `odoo_studio_account__710a64db-6671-46f8-9449-b74311c58aa8` | `account.move` / list | Reactivate + adapt | 1 |
| 3602 | `default_pivot_view_f_062eee08-6efc-4f76-bd73-17f5c753536f` | `account.move` / pivot | Adapt/check | 1 |
| 3603 | `default_pivot_view_f_6393101b-f27a-46f0-a945-2a7c5e2f547a` | `crm.team` / pivot | Adapt/check | 1 |
| 3604 | `odoo_studio_crm_lead_a285568d-c7e6-4c1e-b408-663c45009797` | `crm.lead` / list | Adapt/check | 1 |
| 3605 | `odoo_studio_crm_lead_29c202c0-6df8-4864-b8f4-2b07a4d21787` | `crm.lead` / kanban | Adapt/check | 1 |
| 3606 | `odoo_studio_email_te_02ef52a6-a7fb-4885-9a31-d96b89f85439` | `mail.template` / list | Adapt/check | 1 |
| 3607 | `odoo_studio_sale_ord_7e1b2498-923f-42fc-bb3c-3ae2b6025280` | `sale.order` / list | Adapt/check | 1 |
| 3610 | `odoo_studio_sale_ord_eef97c9e-4a91-4681-9f8f-0f061720a448` | `sale.order` / form | Reactivate + adapt | 1 |
| 3614 | `odoo_studio_account__ad5699e6-19d3-485f-bf0b-06ee3fe89746` | `account.journal` / form | Reactivate + adapt | 1 |
| 3615 | `odoo_studio_ir_cron__7167e7bc-e641-4010-8ee1-6e5987f62f5a` | `ir.cron` / list | Adapt/check | 1 |
| 3616 | `odoo_studio_account__37a70d63-0afb-4ab8-9637-da0c7804a41e` | `account.move` / form | Adapt/check | 2 |
| 3617 | `report_invoice_with__fdd6b841-6c9b-4819-9040-4f6b212ac9ee` | `QWeb` / qweb | Adapt/check | 1 |
| 3618 | `report_invoice_4d9eb516-b40d-4cc0-8dde-ccfac92032b0` | `QWeb` / qweb | Adapt/check | 1 |
| 3619 | `report_invoice_docum_17a6fc97-ee76-4750-a2ed-2fd36eb5f21d` | `QWeb` / qweb | Adapt/check | 26 |
| 3620 | `document_tax_totals_165a4884-15e1-4d86-b966-6ffb1b902b75` | `QWeb` / qweb | Adapt/check | 1 |
| 3621 | `tax_groups_totals_dd327da8-0da3-42df-ae99-b0edf01fa6ca` | `QWeb` / qweb | Adapt/check | 24 |
| 3622 | `document_tax_totals__410ce6c7-0675-45be-9141-1f47844b89fa` | `QWeb` / qweb | Adapt/check | 26 |
| 3623 | `web_studio_backup__e_89042aa0-6ee2-405d-87ca-c12cfb7be5b0` | `QWeb` / qweb | Leave inactive | 23 |
| 3624 | `web_studio_report_ed_fef729ff-bb3e-4b17-8f55-791e2bf99cf2` | `QWeb` / qweb | Adapt/check | 29 |
| 3625 | `web_studio_backup__r_94657ce7-4fa8-4479-9c91-0eb457a21f82` | `QWeb` / qweb | Leave inactive | 26 |
| 3626 | `web_studio_report_ed_5d160e40-367e-4c7c-bbc8-9be94e01da48` | `QWeb` / qweb | Adapt/check | 29 |
| 3627 | `report_invoice_with__6d3edf41-0bcc-4b43-8efa-773bdc56b5ae` | `QWeb` / qweb | Adapt/check | 1 |
| 3628 | `report_invoice_fdc27113-c9a3-4ef5-ae0e-6b2e7885dd3f` | `QWeb` / qweb | Adapt/check | 1 |
| 3629 | `report_invoice_docum_50393010-61b8-4eea-99dc-271f10b3e629` | `QWeb` / qweb | Adapt/check | 26 |
| 3630 | `document_tax_totals_b75308e1-86bc-4f74-b83a-2d56d636add6` | `QWeb` / qweb | Adapt/check | 1 |
| 3631 | `tax_groups_totals_bcc93f5b-e610-4395-a69e-f96e8f3d0af0` | `QWeb` / qweb | Adapt/check | 24 |
| 3632 | `document_tax_totals__5e3b972d-366e-444c-9994-930f874fa3da` | `QWeb` / qweb | Adapt/check | 26 |
| 3633 | `web_studio_backup__r_a17f416e-44b1-402e-95ea-4e1313e1eb61` | `QWeb` / qweb | Leave inactive | 26 |
| 3634 | `web_studio_report_ed_61fdb90d-554c-4d88-b164-e623d79324f7` | `QWeb` / qweb | Adapt/check | 29 |
| 3636 | `odoo_studio_hr_appra_c6324f87-3179-494f-bea9-8d3b1b274bb1` | `hr.appraisal` / form | Adapt/check | 2 |
| 3637 | `odoo_studio_hr_appra_fd089cc0-438e-4a5b-8417-6c0404d988c8` | `hr.appraisal` / list | Reactivate + adapt | 1 |
| 3638 | `default_list_view_fo_a2ca7410-86aa-494c-8ee6-d897735e6ed8` | `x_hr_appraisal_line_f8aaf` / list | Adapt/check | 1 |
| 3639 | `default_form_view_fo_29d1571e-82ff-429d-8976-36dda2ec78c3` | `x_hr_appraisal_line_f8aaf` / form | Adapt/check | 1 |
| 3640 | `default_search_view__5a49e796-4e29-4605-8902-c21d50f8c536` | `x_hr_appraisal_line_f8aaf` / search | Adapt/check | 1 |
| 3641 | `default_pivot_view_f_db7efc22-e4a6-4c4e-9410-bad4cf3d3382` | `hr.appraisal` / pivot | Adapt/check | 1 |
| 3642 | `web_studio_backup__r_bc0622a9-a40e-4843-942a-513e5e694f8c` | `QWeb` / qweb | Leave inactive | 26 |
| 3643 | `web_studio_report_ed_f8832c09-8b9b-455d-b05e-5348a34308b0` | `QWeb` / qweb | Reactivate + adapt | 29 |
| 3644 | `report_saleorder_2377e075-1273-4f4c-af88-7c05c72d1da5` | `QWeb` / qweb | Adapt/check | 1 |
| 3645 | `report_saleorder_raw_5ca54df0-8ebc-4520-8cc3-1d8ce7bc340e` | `QWeb` / qweb | Adapt/check | 1 |
| 3646 | `report_saleorder_doc_614696cf-a1de-448b-84a4-530876feb94a` | `QWeb` / qweb | Adapt/check | 26 |
| 3647 | `document_tax_totals_2808fe82-6c4a-49b6-9dce-6d516391eea0` | `QWeb` / qweb | Adapt/check | 1 |
| 3648 | `tax_groups_totals_41d4f332-778d-43de-8d37-6dac86013a3c` | `QWeb` / qweb | Adapt/check | 24 |
| 3649 | `web_studio_backup__r_aa092532-cb30-4f80-8663-636fad88b1ae` | `QWeb` / qweb | Leave inactive | 26 |
| 3650 | `web_studio_report_ed_a2295005-c415-47be-a3f3-8190219a27b3` | `QWeb` / qweb | Leave inactive | 29 |
| 3651 | `web_studio_backup__d_961693ef-72df-47a1-8eca-39b825c72863` | `QWeb` / qweb | Leave inactive | 26 |
| 3652 | `web_studio_report_ed_5c2838d1-665e-4001-a2dc-a72b2760eee0` | `QWeb` / qweb | Adapt/check | 29 |
| 3653 | `report_invoice_with__a9f185ad-9a43-44c0-902d-0a49ca026d74` | `QWeb` / qweb | Adapt/check | 1 |
| 3654 | `report_invoice_2e1e3c7e-dc84-453c-9186-8a709af8ab8b` | `QWeb` / qweb | Adapt/check | 1 |
| 3655 | `report_invoice_docum_5c9f6b34-adcf-426c-aca3-90dc9438a4e9` | `QWeb` / qweb | Adapt/check | 29 |
| 3656 | `document_tax_totals_d522df4f-44a5-46fa-8c92-f0d840b7add7` | `QWeb` / qweb | Adapt/check | 1 |
| 3657 | `tax_groups_totals_b8809a29-c6cf-48e5-ad68-f5de8ed0a17a` | `QWeb` / qweb | Adapt/check | 24 |
| 3658 | `document_tax_totals__baaf3e58-661f-41d7-9a9c-84cd824e5b7a` | `QWeb` / qweb | Adapt/check | 26 |
| 3659 | `report_invoice_with__28691138-975b-47a7-8543-be7728e8b8bf` | `QWeb` / qweb | Adapt/check | 1 |
| 3660 | `report_invoice_b3f00508-c661-4e2e-af22-acf15a06374e` | `QWeb` / qweb | Adapt/check | 1 |
| 3661 | `report_invoice_docum_ea331e11-8953-44b2-9702-8beac664fc0b` | `QWeb` / qweb | Adapt/check | 29 |
| 3662 | `document_tax_totals_73e8e22d-a013-4cd9-a342-ce1d863b63b8` | `QWeb` / qweb | Adapt/check | 1 |
| 3663 | `tax_groups_totals_90d311ab-5e48-4793-a4a3-b577541ba579` | `QWeb` / qweb | Adapt/check | 24 |
| 3664 | `document_tax_totals__fa170df7-5801-4f6d-8322-9f09a83f9e7a` | `QWeb` / qweb | Adapt/check | 26 |
| 3665 | `odoo_studio_product__71241785-1ddc-4bf0-bda3-356d93a2ab72` | `product.template` / form | Adapt/check | 1 |
| 3666 | `odoo_studio_sale_ord_0ad08280-3dcc-4a5e-8260-a123f82a52f9` | `sale.order` / list | Adapt/check | 1 |
| 3667 | `report_invoice_with__2d3fa55a-6a33-40eb-934e-7c128c61194e` | `QWeb` / qweb | Adapt/check | 1 |
| 3668 | `report_invoice_57e58956-8a30-42ce-8e8b-8e84edfb66ac` | `QWeb` / qweb | Adapt/check | 1 |
| 3669 | `report_invoice_docum_b57267cf-de07-4f4c-a9cd-f2aa5c91d1e7` | `QWeb` / qweb | Adapt/check | 29 |
| 3670 | `document_tax_totals_663ea102-2800-4e5f-b23d-08fda339741c` | `QWeb` / qweb | Adapt/check | 1 |
| 3671 | `tax_groups_totals_ccaaa5cf-6b4f-470f-b683-234096be7ebf` | `QWeb` / qweb | Adapt/check | 24 |
| 3672 | `document_tax_totals__f3436192-ff78-4156-8db7-d6b8e6852382` | `QWeb` / qweb | Adapt/check | 26 |
| 3674 | `default_list_view_fo_1a6ff9db-2c4e-4c64-9cc2-da79e53254a4` | `x_purchase_order_line_7576b` / list | Adapt/check | 1 |
| 3675 | `default_form_view_fo_491991a6-f9e7-4d15-8756-c29e1f359f4a` | `x_purchase_order_line_7576b` / form | Adapt/check | 1 |
| 3676 | `default_search_view__b7b32151-14a7-4d3f-8292-28d4c3b56631` | `x_purchase_order_line_7576b` / search | Adapt/check | 1 |
| 3678 | `odoo_studio_account__c0c5bb7a-ef1e-4177-ae28-ca87d61d5546` | `account.move` / list | Adapt/check | 1 |
| 3685 | `odoo_studio_purchase_9aef22cc-19af-450d-a220-6092b3247066` | `purchase.order` / list | Adapt/check | 1 |
| 3686 | `odoo_studio_payments_5a5cf4a9-f252-4977-b2fd-ec2327f7a355` | `account.move.line` / list | Archive | 1 |
| 3687 | `odoo_studio_account__f650d692-3aa8-4906-85dc-12b6d9d9c41d` | `account.analytic.line` / list | Reactivate + adapt | 1 |
| 3688 | `odoo_studio_hr_emplo_c0ffd91b-cd83-40eb-bb67-b86999ea3ee0` | `hr.employee` / list | Adapt/check | 1 |
| 3690 | `odoo_studio_crm_acti_bfdcbcd3-7056-44e8-a410-4159328bcfdb` | `crm.activity.report` / list | Adapt/check | 1 |
| 3708 | `odoo_studio_account__c2b698ac-fe91-435d-98b1-c0d9be061824` | `account.payment` / list | Reactivate + adapt | 1 |
| 3711 | `odoo_studio_account__2bda6032-1812-42c3-93ed-bfd4d86b1d84` | `account.move.line` / list | Adapt/check | 1 |
| 3712 | `odoo_studio_crm_team_2f32522d-08f4-4e92-be20-d2091d2c0b42` | `crm.team` / list | Adapt/check | 1 |
| 3713 | `odoo_studio_ir_ui_me_7fee5acc-3707-4e4c-86ef-d0f6776a9d4c` | `ir.ui.menu` / list | Adapt/check | 1 |
| 3714 | `odoo_studio_ir_model_d20bb610-67bf-41f5-89ec-9552943e843e` | `ir.model.fields` / list | Adapt/check | 1 |
| 3715 | `odoo_studio_ir_model_40f492e8-8a9e-4533-a5ea-b145d54b81fd` | `ir.model` / list | Adapt/check | 1 |
| 3716 | `report_invoice_with__a5ba460e-53c1-4c07-8d15-feffd43d85fd` | `QWeb` / qweb | Adapt/check | 1 |
| 3717 | `report_invoice_b60f3d23-6436-4545-8f00-8d447d5cda2f` | `QWeb` / qweb | Adapt/check | 1 |
| 3718 | `report_invoice_docum_a71f421d-0e88-4c51-a62a-e92350a04a82` | `QWeb` / qweb | Adapt/check | 27 |
| 3719 | `document_tax_totals_9f0b0634-26db-41fc-a3af-4af4f9ddb9c8` | `QWeb` / qweb | Adapt/check | 1 |
| 3720 | `tax_groups_totals_eb4702a4-2f14-4671-a54a-9b1096d9016c` | `QWeb` / qweb | Adapt/check | 23 |
| 3721 | `document_tax_totals__c74df057-a93a-4de0-a558-4188b9fe292a` | `QWeb` / qweb | Adapt/check | 25 |
| 3727 | `odoo_studio_res_part_c765aec0-a2d4-455c-92eb-678e850c0cba` | `res.partner` / form | Reactivate + adapt | 2 |
| 3728 | `odoo_studio_res_user_adddbe18-5368-4e29-bfb3-52a578b9ddb5` | `res.users` / list | Adapt/check | 1 |
| 3729 | `odoo_studio_account__e1e4af33-8141-479f-8cfb-8034553c8f49` | `account.move.line` / form | Adapt/check | 1 |
