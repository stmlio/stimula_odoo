{
    'name': 'Stimula for Odoo',
    'version': '1.0.0',
    'depends': ['base'],
    'author': 'Romke Jonker',
    'category': 'Extra Tools',
    'summary': 'Zero code data import, export and migration with Simple Table Mapping Language (STML) API for Odoo.',
    'description': '''
    The Stimula for Odoo module provides a zero code data import, export and migration solution for Odoo using the 
    Simple Table Mapping Language (STML) API. STML is a simple, human-readable language that allows you to define 
    data mappings between different systems. The Stimula for Odoo module allows you to import data from, 
    export data to, and migrate data between systems without writing any code. The module is designed 
    to be easy to use, flexible, and extensible. The module is built on top of the Stimula library, which provides a 
    set of tools for working with STML. The Stimula for Odoo module is open source and free to use. 
    For more information, visit https://www.stml.io/odoo_module.
    ''',
    'website': 'https://www.stml.io/odoo_module',
    'external_dependencies': {
        'python': ['stimula>=1.0.0'],
    },
    'data': [
    ],
    'installable': True,
    'license': 'LGPL-3',
    'support': 'support@stml.io',
}
# __manifest__.py
