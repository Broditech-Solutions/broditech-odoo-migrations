"""Targeted repairs for the Studio views audited in the Odoo 17/19 dumps."""

import json
import logging
import re

from lxml import etree

from .studio_crm_rules import CRM_XPATHS

_logger = logging.getLogger(__name__)
CRM_FORM = 'odoo_studio_crm_lead_3067f923-c98e-4f9a-8afc-070b39b06d18'
# These were active in the 17 dump and disabled by the core upgrade, rather
# than by the user. Reactivate only the audited, repaired overlays.
RESTORE_ACTIVE = {
    'odoo_studio_project__452d6f82-b09b-4f03-9abb-1914bdd6c250',
    'odoo_studio_account__cf402e76-b030-45d0-b922-6c81f1629883', CRM_FORM,
    'odoo_studio_crm_lead_2afa26eb-c7d0-45f6-a035-75a8c7cce195',
    'odoo_studio_purchase_a36171a2-b5eb-4d08-94e8-7449b1264c7c',
    'odoo_studio_crossove_8dfd385a-9cb3-40eb-879f-49225bec3d3e',
    'odoo_studio_account__710a64db-6671-46f8-9449-b74311c58aa8',
    'odoo_studio_sale_ord_eef97c9e-4a91-4681-9f8f-0f061720a448',
    'odoo_studio_account__ad5699e6-19d3-485f-bf0b-06ee3fe89746',
    'odoo_studio_hr_appra_fd089cc0-438e-4a5b-8417-6c0404d988c8',
    'web_studio_report_ed_f8832c09-8b9b-455d-b05e-5348a34308b0',
    'odoo_studio_account__f650d692-3aa8-4906-85dc-12b6d9d9c41d',
    'odoo_studio_account__c2b698ac-fe91-435d-98b1-c0d9be061824',
    'odoo_studio_res_part_c765aec0-a2d4-455c-92eb-678e850c0cba',
}
# Removed standard fields have no direct replacement. Retired addon fields
# below are additionally checked against the actual uninstall plan at runtime.
OBSOLETE = {
    'account.journal': {'secure_sequence_id'}, 'hr.appraisal': {'date_final_interview'},
    'res.partner': {'title', 'am_company_type_id', 'am_company_status_type_id'},
    'purchase.order.line': {'analytic_distribution_search'},
}
RETIRED = {
    'account.move': {'payment_mode_id', 'sdd_mandate_id'},
    'account.payment': {'payment_mode_id'},
    'account.move.line': {'payment_mode_id', 'commission_status', 'l10n_es_aeat_349_operation_key'},
    'sale.order': {'payment_mode_id'}, 'sale.order.line': {'commission_status'},
    'res.partner': {'supplier_payment_mode_id', 'customer_payment_mode_id', 'aeat_simplified_invoice', 'agent'},
    'crm.lead': {'location_id'}, 'project.project': {'type_id'},
}
RENAMES = {
    'project.project': {'analytic_account_id': 'account_id', 'display_name': 'name'},
    'budget.analytic': {'crossovered_budget_line': 'budget_line_ids'},
    'account.analytic.line': {'duration_unit_amount': 'unit_amount'},
    'crm.lead': {'mobile': 'phone'},
    'res.partner': {'mobile': 'phone', 'ubl_cii_format': 'invoice_edi_format'},
    'sale.order.line': {'tax_id': 'tax_ids', 'product_uom': 'product_uom_id'},
    'account.move': {'made_sequence_hole': 'made_sequence_gap'},
}
RELATIONS = {
    ('sale.order', 'order_line'): 'sale.order.line',
    ('purchase.order', 'order_line'): 'purchase.order.line',
    ('account.move', 'invoice_line_ids'): 'account.move.line',
    ('crm.lead', 'x_studio_contactos_adicionales'): 'res.partner',
}


def _node_model(node, model, relations):
    # XPath specs are global to the combined architecture. Their final target
    # is a field on the current model, not the field's comodel.
    spec = node if node.tag == 'xpath' else next(node.iterancestors('xpath'), None)
    if spec is not None:
        names = re.findall(r"field\[@name=['\"]([^'\"]+)['\"]\]", spec.get('expr', ''))
        if names and (node is spec or spec.get('position') != 'inside'):
            names = names[:-1]
        if spec.get('expr') == "//field[@name='commission_status']" and model in ('sale.order', 'account.move'):
            model = 'sale.order.line' if model == 'sale.order' else 'account.move.line'
        for name in names:
            model = relations.get((model, name), model)
    for ancestor in reversed(list(node.iterancestors('field'))):
        model = relations.get((model, ancestor.get('name')), model)
    return model


def _drop(node):
    parent = node.getparent()
    if parent is not None:
        parent.remove(node)


def _replace_tokens(text, mapping):
    for old, new in mapping.items():
        text = re.sub(r'\b' + re.escape(old) + r'\b', new, text)
    return text


def adapt_arch(xml, model, name, retired=RETIRED, relations=RELATIONS):
    """Pure XML transformation; never run a report or evaluate expressions."""
    root = etree.fromstring(xml.encode(), etree.XMLParser(resolve_entities=False, no_network=True))
    if name == 'web_studio_report_ed_5c2838d1-665e-4001-a2dc-a72b2760eee0':
        # The audited overlay only added an empty paragraph to a complete copy
        # of the old tax helper. Let the Odoo 19 helper calculate taxes instead.
        return '<data/>'
    if name == CRM_FORM:
        specs = list(root.iter('xpath'))
        if any((s.get('expr') or '').startswith(('/form[1]', '//form[1]')) for s in specs):
            if [s.get('expr') for s in specs] != [old for old, new in CRM_XPATHS]:
                raise RuntimeError('Studio CRM form differs from audited XPath sequence; review before migrating')
            for spec, (old, new) in zip(specs, CRM_XPATHS):
                spec.set('expr', new)
    if model == 'res.partner':
        for spec in root.xpath(".//xpath[@expr=\"//field[@name='agent']\"]"):
            # Keep the inserted industry/event fields when the commission addon goes.
            spec.set('expr', "//field[@name='category_id']")
            # category_id is already the new anchor; moving it after itself is invalid.
            for move in spec.xpath("./xpath[@position='move']"):
                _drop(move)
    if model == 'project.project':
        for spec in root.iter('xpath'):
            expr = spec.get('expr', '')
            if "action_open_technical_dropbox_dashboard" in expr:
                spec.set('expr', "//div[@name='button_box']")
                spec.set('position', 'inside')
            elif "//field[@name='is_template']" == expr and spec.get('position') == 'after':
                spec.set('expr', "//field[@name='user_id']")
    if model == 'sale.order':
        for spec in root.iter('xpath'):
            if spec.get('expr') == "//field[@name='payment_mode_id']":
                spec.set('expr', "//field[@name='payment_term_id']")
    if model == 'account.move':
        for spec in root.iter('xpath'):
            expr = spec.get('expr', '')
            if expr == "//field[@name='amount_total_signed']":
                spec.set('expr', "//field[@name='amount_total_in_currency_signed']")
    if model == 'crm.lead' and name.startswith('odoo_studio_crm_lead_a285568d'):
        for spec in root.iter('xpath'):
            if spec.get('expr') == "//field[@name='x_studio_proyecto_asociado']":
                spec.set('expr', "//field[@name='partner_id']")
    for spec in list(root.iter('xpath')):
        expr = spec.get('expr', '')
        if model == 'account.move' and name.startswith('odoo_studio_account__cf402e76') and expr == "//field[@name='state']":
            spec.set('expr', "//field[@name='status_in_payment']")
        if model == 'project.project' and expr == "//field[@name='is_template']" and spec.get('position') == 'attributes':
            _drop(spec)
        if model == 'purchase.order' and 'confirm_reminder_mail' in expr:
            _drop(spec)
        if model == 'res.partner' and expr == "//form[1]/sheet[1]/group[1]/group[2]/div[3]":
            spec.set('expr', "//field[@name='phone']")
    # Remove unsupported fields/specs. Nonempty specs on removed anchors must
    # have an explicit reanchor above; never silently discard their contents.
    for node in list(root.iter()):
        if not isinstance(node.tag, str):
            continue
        if node.tag == 'tree':
            node.tag = 'list'
        context_model = _node_model(node, model, relations)
        removed = OBSOLETE.get(context_model, set()) | retired.get(context_model, set())
        mapping = RENAMES.get(context_model, {})
        if node.tag == 'field' and node.get('name') in removed:
            _drop(node)
            continue
        if node.tag == 'xpath':
            expr = node.get('expr', '')
            targets = set(re.findall(r"@name=['\"]([^'\"]+)['\"]", expr))
            if targets & removed or 'recompute_lines_agents' in expr:
                meaningful = [c for c in node if c.tag != 'attribute' and c.get('position') != 'move']
                if meaningful:
                    raise RuntimeError(f'Studio {name}: removed anchor still has content: {expr}')
                _drop(node)
                continue
        for attr, value in list(node.attrib.items()):
            node.set(attr, _replace_tokens(value, mapping))
        if node.tag == 'xpath':
            node.set('expr', re.sub(r'\btree\b', 'list', node.get('expr', '')))
        if node.tag == 'field' and model == 'account.analytic.line' and node.get('name') == 'unit_amount':
            node.set('widget', 'float')
    # QWeb copies: preserve layout, replace only references to retired fields
    # and convert the known Odoo 17 report data API to the 19 API.
    for node in list(root.iter()):
        if not isinstance(node.tag, str):
            continue
        for attr, value in list(node.attrib.items()):
            if attr.startswith('t-'):
                if any(re.search(r'\b' + alias + r'\.' + field + r'\b', value)
                       for alias, target_model in (('o', 'account.move'), ('doc', 'sale.order'))
                       for field in retired.get(target_model, ())):
                    _drop(node)
                    break
                value = re.sub(r"(\b(?:line|lines\[line_index\+1\]|lines_to_report\[line_index\+1\])\.display_type) == 'line_section'",
                               r"\1 in ('line_section', 'line_subsection')", value)
                value = re.sub(r'\bline\.product_uom\b', 'line.product_uom_id', value)
                value = re.sub(r'\bline\.tax_id\b', 'line.tax_ids', value)
                if 'line.product_packaging_' in value:
                    _drop(node)
                    break
                node.set(attr, value)
    # Legacy tax helper copies are implementation details, not the custom report
    # layout. Delegate to the maintained 19 templates with the correct currency.
    key = root.get('t-name', '')
    if root.tag == 't' and ('document_tax_totals' in key or 'tax_groups_totals' in key):
        company_currency = 'company_currency' in key
        target = ('account.document_tax_totals_company_currency_template' if company_currency
                  else 'account.document_tax_totals_template')
        # tax_groups_totals copies become unused once their callers delegate.
        currency = 'doc.currency_id' if key.startswith('sale.') else 'o.currency_id'
        for child in list(root):
            root.remove(child)
        root.text = None
        if not company_currency:
            etree.SubElement(root, 't', {'t-set': 'currency', 't-value': currency})
        etree.SubElement(root, 't', {'t-call': target})
    return etree.tostring(root, encoding='unicode')


def migrate(cr, version):
    from .cleanup import cleanup_plan

    _keep, removing = cleanup_plan(cr)
    cr.execute("""
        SELECT v.id, d.name, v.model, v.inherit_id, v.type, v.active, v.arch_db, v.mode, to_jsonb(v)
          FROM ir_ui_view v JOIN ir_model_data d ON d.res_id=v.id
         WHERE d.module='studio_customization' AND d.model='ir.ui.view'
         ORDER BY v.id
    """)
    views = cr.fetchall()
    if not views:
        return
    cr.execute("""
        SELECT f.model, f.name FROM ir_model_fields f
          JOIN ir_model_data d ON d.res_id=f.id AND d.model='ir.model.fields'
         GROUP BY f.id, f.model, f.name HAVING bool_and(d.module IN %s)
    """, (tuple(removing) or ('',),))
    removed_fields = set(cr.fetchall())
    cr.execute("SELECT model, name, relation FROM ir_model_fields")
    fields = cr.fetchall()
    existing = {(model, name) for model, name, relation in fields}
    relations = dict(RELATIONS)
    relations.update({(model, name): relation for model, name, relation in fields if relation})
    retired = {model: {name for name in names if (model, name) in removed_fields or (model, name) not in existing}
               for model, names in RETIRED.items()}
    cr.execute("""
        SELECT v.id, v.inherit_id, d.module
          FROM ir_ui_view v LEFT JOIN ir_model_data d
            ON d.model='ir.ui.view' AND d.res_id=v.id
    """)
    parents, owners = {}, {}
    for vid, parent, module in cr.fetchall():
        parents[vid] = parent
        if module:
            owners.setdefault(vid, set()).add(module)
    cr.execute("""
        CREATE TABLE IF NOT EXISTS broditech_studio_view_backup (
            view_id INTEGER PRIMARY KEY, xmlid VARCHAR NOT NULL,
            original JSONB NOT NULL, migrated_arch JSONB, reason TEXT NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
        )
    """)
    cr.execute("SELECT view_id FROM broditech_studio_view_backup")
    previously_migrated = {row[0] for row in cr.fetchall()}
    changed = archived = 0
    for vid, name, model, parent, kind, active, arches, mode, original in views:
        if isinstance(arches, str):
            arches = json.loads(arches)
        if not arches:
            raise RuntimeError(f'Studio {name} has no architecture')
        ancestor = parent
        visited = set()
        orphan = False
        while ancestor and ancestor not in visited:
            visited.add(ancestor)
            if owners.get(ancestor) and owners[ancestor] <= set(removing):
                orphan = True
                break
            ancestor = parents.get(ancestor)
        if not active and name not in RESTORE_ACTIVE and not orphan:
            continue
        migrated = arches if orphan else {lang: adapt_arch(xml, model, name, retired, relations) for lang, xml in arches.items()}
        new_active = False if orphan else (active or (vid not in previously_migrated and name in RESTORE_ACTIVE))
        reason = 'retired parent addon' if orphan else 'Odoo 19 Studio compatibility'
        if migrated == arches and new_active == active and not orphan:
            continue
        # No FK: retain the audit snapshot even if uninstall removes the model.
        snapshot = json.dumps(original)
        cr.execute("""
            INSERT INTO broditech_studio_view_backup (view_id, xmlid, original, reason)
            VALUES (%s,%s,%s::jsonb,%s) ON CONFLICT (view_id) DO NOTHING
        """, (vid, 'studio_customization.' + name, snapshot, reason))
        cr.execute("""
            UPDATE ir_ui_view SET arch_db=%s::jsonb, active=%s, inherit_id=%s, mode=%s WHERE id=%s
        """, (json.dumps(migrated), new_active, None if orphan else parent, 'primary' if orphan else mode, vid))
        cr.execute("UPDATE broditech_studio_view_backup SET migrated_arch=%s::jsonb WHERE view_id=%s",
                   (json.dumps(migrated), vid))
        changed += 1
        archived += orphan
        _logger.info('Adapted Studio view studio_customization.%s (%s)', name, reason)
    _logger.info('Studio view migration: %d inspected, %d changed, %d archived',
                 len(views), changed, archived)
