"""Audit Studio SQL dumps without restoring them or connecting to a database.

Optional source-aware XPath replay uses Odoo's own pure inheritance helper.
Only view inventories and diagnostics are written to the output, never dumps.
"""

import argparse
import ast
import collections
import copy
import html
import subprocess

from lxml import etree as E
from broditech_odoo_migrations.studio_views import adapt_arch, RESTORE_ACTIVE, RELATIONS, RETIRED, OBSOLETE

import json,re,sys
from pathlib import Path
TABLES={'ir_ui_view','ir_model_data','ir_model_fields','ir_module_module','ir_model','ir_module_module_dependency'}
ESC={'b':'\b','f':'\f','n':'\n','r':'\r','t':'\t','v':'\v','\\':'\\'}
def decode(v):
    if v=='\\N': return None
    return re.sub(r'\\([0-7]{1,3}|x[0-9a-fA-F]{1,2}|.)',lambda m: chr(int(m[1],16)) if m[1].startswith('x') else chr(int(m[1],8)) if m[1][0] in '01234567' else ESC.get(m[1],m[1]),v)
def read_dump(path):
    result={}; table=None
    with open(path) as f:
        for line in f:
            if line.startswith('COPY public.'):
                m=re.match(r'COPY public\.(\w+) \((.*?)\) FROM stdin;',line)
                table=m[1] if m and m[1] in TABLES else None
                if table:
                    columns=[v.strip().strip('"') for v in m[2].split(',')];result[table]=[]
            elif table:
                if line=='\\.\n':table=None;continue
                values=[decode(v) for v in line.rstrip('\n').split('\t')]
                assert len(values)==len(columns),(table,len(values),len(columns))
                result[table].append(dict(zip(columns,values)))
    return result


def source_views(data, roots):
    xmlids={r['module']+'.'+r['name']:r['res_id'] for r in data['ir_model_data'] if r['model']=='ir.ui.view'}
    allids={r['module']+'.'+r['name']:r['res_id'] for r in data['ir_model_data']}
    result={}
    for root in roots:
        for module in root.iterdir():
            if not (module/'__manifest__.py').exists():continue
            for sub in ('views','report','data'):
                folder=module/sub
                if not folder.exists():continue
                for path in folder.rglob('*.xml'):
                    try:tree=E.parse(str(path))
                    except E.XMLSyntaxError:continue
                    for record in tree.xpath('//record[@model="ir.ui.view"]|//template[@id]'):
                        key=record.get('id')
                        if not key:continue
                        key=key if '.' in key else module.name+'.'+key
                        if key not in xmlids:continue
                        current=result.setdefault(xmlids[key],{})
                        if record.tag=='record':
                            for field in record.findall('field'):
                                name=field.get('name')
                                if name=='arch':
                                    if len(field)==1:a=copy.deepcopy(field[0])
                                    else:
                                        a=E.Element('data')
                                        for child in field:a.append(copy.deepcopy(child))
                                    current['arch']=E.tostring(a,encoding='unicode')
                                elif name=='inherit_id':
                                    ref=field.get('ref')
                                    if ref:current['inherit_xmlid']=ref if '.' in ref else module.name+'.'+ref
                                elif name in ('priority','mode'):current[name]=field.text or field.get('eval')
                        else:
                            a=E.Element('data' if record.get('inherit_id') else 't')
                            if not record.get('inherit_id'):a.set('t-name',key)
                            for child in record:a.append(copy.deepcopy(child))
                            current['arch']=E.tostring(a,encoding='unicode')
                            if record.get('inherit_id'):current['inherit_xmlid']=record.get('inherit_id')
                            if record.get('primary') in ('True','true','1'):current['mode']='primary'
                        if 'arch' in current:
                            current['arch']=re.sub(r'%\(([^)]+)\)d',lambda m:allids.get(m[1] if '.' in m[1] else module.name+'.'+m[1],m[1]),current['arch'])
    return result


def replay(data, studio, transformed, source, roots, custom_root=None):
    # Execute only the official standalone XML helper. Translation/error stubs
    # avoid importing Odoo or initializing a registry in this offline audit.
    path=source/'odoo/tools/template_inheritance.py'
    code='\n'.join(line for line in path.read_text().splitlines()
                   if not line.startswith(('from odoo.', 'from .misc')))
    ns={'__name__':'studio_offline_inheritance', 'SKIPPED_ELEMENT_TYPES':(E._Comment,E._ProcessingInstruction),
        'html_escape':html.escape,'ValidationError':ValueError,
        'LazyTranslate':lambda name:lambda msg,*args:msg % args if args else msg}
    exec(compile(code,str(path),'exec'),ns)
    apply=ns['apply_inheritance_specs']
    E.FunctionNamespace(None)['hasclass']=lambda context,*names:all(n in (context.context_node.get('class') or '').split() for n in names)
    views={r['id']:dict(r) for r in data['ir_ui_view']}
    ids={r['res_id']:r['module']+'.'+r['name'] for r in data['ir_model_data'] if r['model']=='ir.ui.view'}
    byxml={value:key for key,value in ids.items()}
    standard=set(subprocess.check_output(['git','-C',str(source),'ls-tree','--name-only','HEAD:addons'],text=True).splitlines())
    standard.update(p.name for root in roots for p in root.iterdir()
                    if (p/'__manifest__.py').exists() and root != custom_root)
    keep=standard|{'studio_customization','am_integration','am_project','disable_vat_check'}
    removing={r['name'] for r in data['ir_module_module'] if r['state'] in ('installed','to upgrade','to remove','to install')}-keep
    current=source_views(data,roots)
    for vid,info in current.items():
        if 'arch' in info:views[vid]['arch_db']=json.dumps({'en_US':info['arch']})
        if info.get('inherit_xmlid') in byxml:views[vid]['inherit_id']=byxml[info['inherit_xmlid']]
        for name in ('mode','priority'):
            if info.get(name):views[vid][name]=info[name]
    for vid,arches in transformed.items():
        views[vid]['arch_db']=json.dumps(arches)
        if studio[vid]['name'] in RESTORE_ACTIVE:views[vid]['active']='t'
        if studio[vid]['action']=='archive':views[vid]['active']='f'
    children=collections.defaultdict(list)
    for view in views.values():
        if view['inherit_id'] and view['active']=='t' and view['mode']!='primary' and ids.get(view['id'],'').split('.')[0] not in removing:
            children[view['inherit_id']].append(view)
    errors=[];combined={}
    def root(vid):
        while views[vid]['inherit_id'] and views[vid]['mode']!='primary':vid=views[vid]['inherit_id']
        return vid
    def combine(vid):
        if vid in combined:return copy.deepcopy(combined[vid])
        view=views[vid];tree=E.fromstring(json.loads(view['arch_db'])['en_US'].encode())
        if view['inherit_id'] and view['mode']=='primary':tree=apply(combine(view['inherit_id']),tree)
        def extend(parent,tree):
            for child in sorted(children[parent],key=lambda v:(int(v['priority']),int(v['id']))):
                try:
                    tree=apply(tree,E.fromstring(json.loads(child['arch_db'])['en_US'].encode()))
                    tree=extend(child['id'],tree)
                except ValueError as error:errors.append({'xmlid':ids.get(child['id'],child['id']),'error':str(error)})
            return tree
        tree=extend(vid,tree);combined[vid]=copy.deepcopy(tree);return tree
    fields={(r['model'],r['name']):r for r in data['ir_model_fields']}
    relations={key:f['relation'] for key,f in fields.items() if f['relation']};relations.update(RELATIONS)
    checked=set()
    def check_fields(node,model):
        for child in node:
            target=model
            if child.tag=='field':
                key=(model,child.get('name'))
                if key not in fields and child.get('name') not in ('id','display_name'):
                    errors.append({'model':model,'missing_field':child.get('name')})
                target=relations.get(key,model)
            check_fields(child,target)
    translations=0
    for vid,item in studio.items():
        if item['action'] in ('archive','leave inactive'):continue
        rid=root(vid)
        try:
            tree=combine(rid)
            if rid not in checked and views[rid]['type']!='qweb':check_fields(tree,views[rid]['model'])
            checked.add(rid)
            if views[vid]['inherit_id']:
                parent=combine(root(views[vid]['inherit_id']))
                # Validate translated XPath expressions against the same semantic
                # parent; actual QWeb expression evaluation requires live Odoo.
                for lang,xml in transformed[vid].items():
                    # The combined parent already includes this extension. Use
                    # the default-language replay for that view; translation
                    # skeleton equality confirms locale-independent selectors.
                    default=E.fromstring(transformed[vid]['en_US'].encode())
                    localized=E.fromstring(xml.encode())
                    if [x.get('expr') for x in default.iter('xpath')] != [x.get('expr') for x in localized.iter('xpath')]:
                        errors.append({'xmlid':item['xmlid'],'language':lang,'error':'translated XPath skeleton differs'})
                    translations+=1
        except ValueError as error:errors.append({'xmlid':item['xmlid'],'error':str(error)})
    return {'roots_checked':len(checked),'translated_inherited_architectures':translations,
            'source_view_definitions':len(current),'source_commit':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),
            'errors':errors}


def audit(before,after):
    old={r['res_id']:r for r in before['ir_model_data'] if r['module']=='studio_customization' and r['model']=='ir.ui.view'}
    oldviews={r['id']:r for r in before['ir_ui_view']}
    views={r['id']:r for r in after['ir_ui_view']}
    ids={r['res_id']:r['module']+'.'+r['name'] for r in after['ir_model_data'] if r['model']=='ir.ui.view'}
    studio={};transformed={};translation_count=0
    for row in after['ir_model_data']:
        if row['module']!='studio_customization' or row['model']!='ir.ui.view' or row['res_id'] not in views:continue
        vid=row['res_id'];view=views[vid];arches=json.loads(view['arch_db']);translation_count+=len(arches)
        name=row['name'];parent=ids.get(view['inherit_id']);action='adapt' if view['active']=='t' or name in RESTORE_ACTIVE else 'leave inactive'
        if parent and parent.split('.')[0] in ('crm_salesperson_planner','account_due_list'):action='archive'
        new={lang:adapt_arch(xml,view['model'],name) for lang,xml in arches.items()} if action=='adapt' else arches
        transformed[vid]=new
        for lang,xml in new.items():
            parsed=E.fromstring(xml.encode())
            if action=='adapt' and adapt_arch(xml,view['model'],name)!=xml:raise ValueError(f'Non-idempotent view {name}/{lang}')
            if view['type']=='qweb' and action=='adapt':
                for node in parsed.iter():
                    for attr,value in node.attrib.items():
                        if attr in ('t-if','t-elif','t-value','t-out','t-esc','t-foreach','t-field','t-options') or attr.startswith('t-att-'):
                            ast.parse(value,mode='eval')
                    if 't-else' in node.attrib or 't-elif' in node.attrib:
                        previous=node.getprevious()
                        while previous is not None and not isinstance(previous.tag,str):previous=previous.getprevious()
                        if previous is None or not ({'t-if','t-elif'} & set(previous.attrib)):raise ValueError(f'Unmatched QWeb branch in {name}/{lang}')
        studio[vid]={'id':vid,'name':name,'xmlid':'studio_customization.'+name,'model':view['model'],'type':view['type'],
                     'parent':parent,'active_17':oldviews.get(vid,{}).get('active')=='t','active_19':view['active']=='t',
                     'action':action,'architecture_changed':new!=arches,'languages':len(arches)}
    return studio,transformed,{'studio_views_17':len(old),'studio_views_19':len(studio),'translated_architectures':translation_count,
                               'types':dict(collections.Counter(v['type'] for v in studio.values())),
                               'actions':dict(collections.Counter(v['action'] for v in studio.values())),
                               'reactivated':sum(v['active_17'] and not v['active_19'] and v['action']=='adapt' for v in studio.values())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',type=Path,required=True);parser.add_argument('--after',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--odoo-source',type=Path)
    parser.add_argument('--enterprise-addons',type=Path);parser.add_argument('--custom-addons',type=Path)
    args=parser.parse_args()
    before=read_dump(args.before);after=read_dump(args.after)
    studio,transformed,summary=audit(before,after)
    report={'summary':summary,'views':list(studio.values())}
    if args.odoo_source:
        roots=[args.odoo_source/'odoo/addons',args.odoo_source/'addons']
        if args.enterprise_addons:roots.append(args.enterprise_addons)
        if args.custom_addons:roots.append(args.custom_addons)
        report['replay']=replay(after,studio,transformed,args.odoo_source,roots,args.custom_addons)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(summary))
    if report.get('replay',{}).get('errors'):
        print(json.dumps(report['replay']['errors']));raise SystemExit(1)
    if 'replay' in report:print(json.dumps({k:v for k,v in report['replay'].items() if k!='errors'}))


if __name__=='__main__':main()
