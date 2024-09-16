# __manifest__.py
{
    'name': 'Stimula for Odoo',
    'version': '1.0',
    'summary': 'Adds Simple Table Mapping Language (STML) API to Odoo',
    'author': 'Romke Jonker',
    'website': 'https://www.stml.io/odoo_module',
    'category': 'Custom',
    'depends': ['base'],
    'external_dependencies': {
        'python': ['stimula>=0.0.18'],
    },
    'data': [
        # List of XML or CSV files to be loaded
        # 'controllers/main.py'
    ],
    'installable': True,
    'license': 'LGPL-3',
}
