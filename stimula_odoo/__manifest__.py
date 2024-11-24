{
    'name': 'Stimula for Odoo',
    'version': '1.2.3',
    'depends': ['base'],
    'author': 'STML.IO',
    'category': 'Extra Tools',
    'summary': 'Easy data import, export and migration with Simple Table Mapping Language (STML) for Odoo.',
    'description': '''
    STML, or Simple Table Mapping Language, is a simple, human readable language designed for mapping data between CSV files 
    and SQL databases. It forms the foundation for data import and export, enabling data analysts and developers 
    to define fields, transformations, foreign key resolutions, and row selections in a simple, repeatable, and reusable way.
    For more information, visit https://www.stml.io/odoo_module.
    ''',
    'website': 'https://www.stml.io/odoo_module',
    'external_dependencies': {
        'python': ['stimula'],
    },
    'data': [
    ],
    'installable': True,
    'license': 'LGPL-3',
    'support': 'support@stml.io',
    'images': ['static/description/banner.png'],
}
# __manifest__.py
