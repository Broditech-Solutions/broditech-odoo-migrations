import json
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch

from lxml import etree as E
from broditech_odoo_migrations import studio_views as studio
from broditech_odoo_migrations.studio_crm_rules import CRM_XPATHS


class XMLTests(unittest.TestCase):
    def adapt(self, xml, model='sale.order', name='example', **kwargs):
        return E.fromstring(studio.adapt_arch(xml, model, name, **kwargs).encode())

    def test_nested_line_field_renames_and_commission_removal(self):
        root = self.adapt('''<data>
          <xpath expr="//field[@name='order_line']/tree/field[@name='tax_id']" position="attributes"><attribute name="column_invisible">True</attribute></xpath>
          <xpath expr="//field[@name='commission_status']" position="attributes"><attribute name="invisible">True</attribute></xpath>
          <xpath expr="//field[@name='payment_mode_id']" position="after"><xpath expr="//field[@name='user_id']" position="move"/></xpath>
        </data>''')
        self.assertIn("field[@name='tax_ids']", root[0].get('expr'))
        self.assertIn('/list/', root[0].get('expr'))
        self.assertEqual(root[1].get('expr'), "//field[@name='payment_term_id']")
        self.assertEqual(len(root), 2)

    def test_field_names_are_scoped_to_models_and_retained_dependencies(self):
        xml='<data><xpath expr="//field[@name=\'name\']" position="after"><field name="type_id"/></xpath></data>'
        self.assertEqual(len(self.adapt(xml, 'res.partner').xpath('.//field')), 1)
        self.assertEqual(len(self.adapt(xml, 'project.project').xpath('.//field')), 0)
        self.assertEqual(len(self.adapt(xml, 'project.project', retired={}).xpath('.//field')), 1)

    def test_never_discards_custom_fields_on_unhandled_removed_anchor(self):
        with self.assertRaisesRegex(RuntimeError, 'removed anchor still has content'):
            self.adapt('<data><xpath expr="//field[@name=\'commission_status\']" position="after"><field name="x_studio_keep"/></xpath></data>')

    def test_project_and_partner_reanchors_preserve_customizations(self):
        p=self.adapt('<data><xpath expr="//button[@name=\'action_open_technical_dropbox_dashboard\']" position="after"><button name="custom_action"/></xpath></data>', 'project.project')
        self.assertEqual((p[0].get('expr'), p[0].get('position')), ("//div[@name='button_box']", 'inside'))
        p=self.adapt('<data><xpath expr="//field[@name=\'agent\']" position="after"><field name="x_studio_eventos"/><xpath expr="//field[@name=\'category_id\']" position="move"/></xpath></data>', 'res.partner')
        self.assertEqual(p[0].get('expr'), "//field[@name='category_id']")
        self.assertEqual(p[0][0].get('name'), 'x_studio_eventos')
        self.assertFalse(p.xpath('.//xpath[@position="move"]'))

    def test_crm_rewrites_each_operation_with_a_strict_sequence_guard(self):
        root=E.Element('data')
        for old,new in CRM_XPATHS:E.SubElement(root,'xpath',expr=old)
        adapted=studio.adapt_arch(E.tostring(root,encoding='unicode'),'crm.lead',studio.CRM_FORM)
        self.assertNotIn('/form[1]',adapted)
        self.assertEqual(studio.adapt_arch(adapted,'crm.lead',studio.CRM_FORM),adapted)
        root[0].set('expr', '//form[1]/new_user_edit')
        with self.assertRaisesRegex(RuntimeError,'differs from audited'):
            studio.adapt_arch(E.tostring(root,encoding='unicode'),'crm.lead',studio.CRM_FORM)

    def test_report_tax_helpers_delegate_to_current_api_and_keep_template_keys(self):
        for key,target,currency in (
            ('account.document_tax_totals_copy_1','account.document_tax_totals_template','o.currency_id'),
            ('sale.document_tax_totals_copy_1','account.document_tax_totals_template','doc.currency_id'),
            ('account.document_tax_totals_company_currency_template_copy_1','account.document_tax_totals_company_currency_template',None),
        ):
            root=self.adapt(f'<t t-name="{key}"><span t-out="tax_totals[\'groups_by_subtotal\']"/></t>', None)
            self.assertEqual(root.get('t-name'),key)
            self.assertEqual(root[-1].get('t-call'),target)
            if currency:self.assertEqual(root[0].get('t-value'),currency)
            self.assertNotIn('groups_by_subtotal',E.tostring(root,encoding='unicode'))

    def test_report_layout_survives_without_retired_payment_or_packaging_fields(self):
        xml='''<t t-name="custom_invoice"><div name="custom_design"><span t-field="o.x_studio_proyecto"/><p t-if="o.payment_mode_id"><span t-field="o.payment_mode_id.note"/></p><div t-if="o.sdd_mandate_id"/><span t-field="line.product_uom"/><span t-field="line.tax_id"/><span t-if="line.product_packaging_id"><span t-field="line.product_packaging_qty"/></span></div></t>'''
        root=self.adapt(xml,None)
        result=E.tostring(root,encoding='unicode')
        self.assertIn('custom_design',result)
        self.assertIn('o.x_studio_proyecto',result)
        self.assertIn('line.product_uom_id',result)
        self.assertIn('line.tax_ids',result)
        for obsolete in ('payment_mode_id','sdd_mandate_id','product_packaging'):self.assertNotIn(obsolete,result)
        self.assertEqual(studio.adapt_arch(result,None,'example'),result)


class BoolAnd:
    def __init__(self):self.value=True
    def step(self,value):self.value &= bool(value)
    def finalize(self):return self.value


class Cursor:
    def __init__(self):
        self.db=sqlite3.connect(':memory:')
        self.db.create_aggregate('bool_and',1,BoolAnd)
        self.db.executescript('''
          CREATE TABLE ir_ui_view (id INTEGER PRIMARY KEY, model TEXT, inherit_id INTEGER, type TEXT, active BOOLEAN, arch_db TEXT, mode TEXT);
          CREATE TABLE ir_model_data (id INTEGER PRIMARY KEY, module TEXT, name TEXT, model TEXT, res_id INTEGER);
          CREATE TABLE ir_model_fields (id INTEGER PRIMARY KEY, model TEXT, name TEXT, relation TEXT);
        ''')

    def view(self,vid,name,xml,active=True,parent=None,module='studio_customization',model='res.partner'):
        arches={'en_US':xml,'es_ES':xml.replace('Custom','Personalizado')}
        self.db.execute('INSERT INTO ir_ui_view VALUES (?,?,?,?,?,?,?)',(vid,model,parent,'form',active,json.dumps(arches),'extension' if parent else 'primary'))
        self.db.execute('INSERT INTO ir_model_data(module,name,model,res_id) VALUES (?,?,?,?)',(module,name,'ir.ui.view',vid))

    def execute(self,query,params=()):
        self.original_row='to_jsonb(v)' in query
        query=query.replace('to_jsonb(v)',"json_object('id',v.id,'arch_db',json(v.arch_db),'active',v.active,'inherit_id',v.inherit_id,'mode',v.mode,'model',v.model)")
        query=query.replace('::jsonb','').replace('DEFAULT NOW()','DEFAULT CURRENT_TIMESTAMP')
        values=[]
        for param in params:
            if isinstance(param,tuple):
                query=query.replace('%s','('+','.join('?' for _ in param)+')',1);values.extend(param)
            else:query=query.replace('%s','?',1);values.append(param)
        self.result=self.db.execute(query,values)

    def fetchall(self):
        rows=self.result.fetchall()
        if self.original_row:return [(*row[:-1],json.loads(row[-1])) for row in rows]
        return rows


class MigrationTests(unittest.TestCase):
    def run_migration(self,cr):
        cleanup=types.ModuleType('broditech_odoo_migrations.cleanup')
        cleanup.cleanup_plan=lambda cr:({'studio_customization','web_studio'},['retired'])
        with patch.dict(sys.modules,{'broditech_odoo_migrations.cleanup':cleanup}):studio.migrate(cr,None)

    def test_preserves_translations_originals_and_user_disable_on_rerun(self):
        cr=Cursor();name='odoo_studio_account__ad5699e6-19d3-485f-bf0b-06ee3fe89746'
        xml='<data><xpath expr="//field[@name=\'currency_id\']" position="after"><field name="secure_sequence_id"/><field name="sequence" string="Custom"/></xpath></data>'
        cr.view(1,name,xml,False,model='account.journal')
        self.run_migration(cr)
        arch,active=cr.db.execute('SELECT arch_db,active FROM ir_ui_view WHERE id=1').fetchone()
        self.assertEqual(active,1)
        self.assertNotIn('secure_sequence_id',arch)
        self.assertIn('Personalizado',json.loads(arch)['es_ES'])
        backup=cr.db.execute('SELECT original FROM broditech_studio_view_backup').fetchone()[0]
        self.assertIn('secure_sequence_id',backup)
        cr.db.execute('UPDATE ir_ui_view SET active=0 WHERE id=1')
        self.run_migration(cr)
        self.assertEqual(cr.db.execute('SELECT active FROM ir_ui_view WHERE id=1').fetchone()[0],0)
        self.assertEqual(cr.db.execute('SELECT original FROM broditech_studio_view_backup').fetchone()[0],backup)

    def test_archives_orphan_before_parent_uninstall_and_leaves_user_backups_alone(self):
        cr=Cursor();xml='<data><xpath expr="//form" position="inside"><field name="x_studio_old"/></xpath></data>'
        cr.view(99,'parent','<form/>',module='retired')
        cr.view(1,'orphan',xml,parent=99)
        cr.view(2,'web_studio_backup__example',xml,False)
        self.run_migration(cr)
        row=cr.db.execute('SELECT inherit_id,active,mode,arch_db FROM ir_ui_view WHERE id=1').fetchone()
        self.assertEqual(row[:3],(None,0,'primary'))
        self.assertEqual(json.loads(row[3])['en_US'],xml)
        self.assertEqual(cr.db.execute('SELECT view_id FROM broditech_studio_view_backup').fetchall(),[(1,)])

    def test_no_studio_views_is_noop(self):
        cr=Cursor();self.run_migration(cr)
        self.assertIsNone(cr.db.execute("SELECT name FROM sqlite_master WHERE name='broditech_studio_view_backup'").fetchone())
