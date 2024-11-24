"""
    rest.py

    Copyright (C) 2024 STML.IO

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Lesser General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public License
    along with this program. If not, see <https://www.gnu.org/licenses/>.

    Developer: Romke Jonker
    Contact: romke@stml.io
    Description: This script provides the Stimula REST controller. It takes care of handling requests, parsing parameters and invoking the Stimula library.
It wraps each call with handlers for authentication, database connection and exceptions.
"""
import logging
import random
import string
import traceback
from functools import wraps

from jwt import InvalidSignatureError
from sqlalchemy import create_engine
from stimula.service.context import cnx_context
from stimula.service.db import DB

from odoo import http, api, registry
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.modules.registry import Registry
from .odoo_auth import OdooAuth
from .odoo_orm import OdooORM

_logger = logging.getLogger(__name__)


def exception_handler(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            # Call the original function
            return f(*args, **kwargs)
        except Exception as e:
            # find root cause
            while (e.__cause__ is not None) and (e.__cause__ is not e):
                e = e.__cause__

            # collect error information
            error_object = {
                'msg': str(e),
                'short': str(e).split('\n', 1)[0],
                'type': type(e).__name__,
                'trace': traceback.format_exc(),
            }

            # get specific error status
            error_status = 401 if isinstance(e, AccessDenied) or isinstance(e, InvalidSignatureError) else 400

            return request.make_json_response(error_object, status=error_status)

    return wrapper


def authentication_handler(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        # get authorization header
        authorization_header = request.httprequest.headers['Authorization']

        if not authorization_header:
            return "Authorization header missing", 401

        # Check if the header starts with "Bearer "
        if not authorization_header.startswith('Bearer '):
            return "Invalid Authorization header format", 401

        # Extract the token (excluding "Bearer ")
        token = authorization_header[len('Bearer '):]

        # validate the token
        database, uid, username = StimulaController._auth.validate_token(token)

        cnx_context.database = database
        cnx_context.uid = uid
        cnx_context.username = username

        return f(*args, **kwargs)

    return wrapper


def connection_handler(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        database = cnx_context.database
        registry = Registry(database)

        # store registry in cnx_context
        cnx_context.registry = registry
        # get cursor the Odoo way
        cnx_context.cr = registry.cursor()
        # get connection from cursor. Odoo doesn't directly expose the connection object, but it's useful to have for libraries like pandas
        cnx_context.cnx = cnx_context.cr.connection
        # also create sqlalchemy engine, bec/ that's what pandas needs
        cnx_context.engine = create_engine('postgresql://', creator=lambda: cnx_context.cnx)
        # Call the original function
        return f(*args, **kwargs)

    return wrapper


class StimulaController(http.Controller):
    def __init__(self):
        _logger.log(logging.INFO, 'StimulaController.__init__')
        # create an OdooAuth object with functions to retrieve secret key and token lifetime
        StimulaController._auth = OdooAuth(self.get_secret_key, self.get_token_lifetime)
        # create an OdooORM object with a function to retrieve the current environment
        self._db = DB(orm_function=self._orm_function)

    def _orm_function(self):
        _logger.log(logging.INFO, 'StimulaController._orm_function')
        # Create an environment with the current context and new user
        env = api.Environment(cnx_context.cr, cnx_context.uid, {})
        return OdooORM(env)

    def get_secret_key(self, database):
        key = 'stimula_odoo.secret_key'
        # generator to create a default random secret key
        default_generator = lambda: ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        return self.get_or_set_param(database, key, default_generator)

    def get_token_lifetime(self, database):
        key = 'stimula_odoo.token_lifetime'
        # generator to create a default token lifetime of 24 hours
        default_generator = lambda: 60 * 60 * 24
        return int(self.get_or_set_param(database, key, default_generator))

    def get_or_set_param(self, database, key, default_generator):
        registry_instance = registry(database)
        with registry_instance.cursor() as cr:
            env = api.Environment(cr, 1, {})
            config_params = env['ir.config_parameter']
            # get odoo configuration parameter from database
            if not config_params.get_param(key):
                # generate default value
                default = default_generator()
                # set default if not already set
                config_params.set_param(key, default)

            return config_params.get_param(key)

    def get_param(self, key, default=None):
        env = http.request.env
        assert env, 'Environment not set, is a database available?'
        return env['ir.config_parameter'].sudo().get_param(key, default)

    def set_param(self, key, value):
        env = http.request.env
        assert env, 'Environment not set, is a database available?'
        env['ir.config_parameter'].sudo().set_param(key, value)

    @http.route('/stimula/1.0/hello', type='http', auth='none', methods=['GET'], csrf=False)
    def hello(self):
        _logger.info('hello')
        return 'This is the Stimula REST API.'

    @http.route('/stimula/1.0/auth', type='http', auth='none', methods=['POST'], csrf=False)
    @exception_handler
    def authenticate(self, **post):
        # get database from form data
        database = post.get('database')

        # if no database is provided, then try to resolve based on the request context.
        # This is useful when running in a single-database configuration when it's not easy to find the database name,
        # like on an odoo.sh production build.
        if not database:
            # and if this request is served from a db context
            if hasattr(request, 'env') and hasattr(request.env, 'cr') and hasattr(request.env.cr, 'dbname'):
                # then use the current db context
                database = request.env.cr.dbname
            else:
                # otherwise, raise an exception
                raise Exception('No database provided. Either provide a database parameter or run this request from a single database configuration.')

        # authenticate the posted credentials. Always validate we can connect.
        token = self._auth.authenticate(database, post['username'], post['password'])

        # return the token
        return request.make_json_response({'token': token})

    @http.route('/stimula/1.0/tables', type='http', auth='none', methods=['GET'], csrf=False)
    @exception_handler
    @authentication_handler
    @connection_handler
    def get_tables(self, **query):
        _logger.info('get_tables %s', query)

        # optional query parameter to filter results
        q_param = query.get('q')
        tables = self._db.get_tables(q_param)
        return request.make_json_response(tables)

    @http.route('/stimula/1.0/tables/<string:table_name>/header', type='http', auth='none', methods=['GET'], csrf=False)
    @exception_handler
    @authentication_handler
    @connection_handler
    def get_header(self, table_name, **query):
        # header is optional
        h_param = query.get('h')

        # supported styles: [json], csv
        style_param = query.get('style')
        assert style_param in [None, '', 'csv', 'json'], 'Invalid style parameter'

        if style_param == 'csv':
            csv_header = self._db.get_header_csv(table_name, h_param)
            response = request.make_response(csv_header)
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = 'attachment; filename=mydata.csv'
            return response

        json_header = self._db.get_header_json(table_name, h_param)
        return request.make_json_response(json_header)

    @http.route('/stimula/1.0/tables/<string:table_name>/count', type='http', auth='none', methods=['GET'], csrf=False)
    @exception_handler
    @authentication_handler
    @connection_handler
    def get_count(self, table_name, **query):
        # header is optional, fall back on default header if none is provided
        h_param = query.get('h')

        # where clause is optional, use to restrict returned rows
        q_param = query.get('q')

        count = self._db.get_count(table_name, h_param, q_param)
        return request.make_json_response({'count': count})

    @http.route('/stimula/1.0/tables/<string:table_name>', type='http', auth='none', methods=['GET'], csrf=False)
    @exception_handler
    @authentication_handler
    @connection_handler
    def get_table(self, table_name, **query):
        # optional header parameter, fall back to default header if none is provided
        header = query.get('h')

        # optional where clause parameter, fall back to all rows if none is provided
        where_clause = query.get('q')

        # get table contents, use header if provided, create default header otherwise
        csv_output = self._db.get_table_as_csv(table_name, header, where_clause)

        # Create a response object with CSV data and appropriate headers
        response = request.make_response(csv_output)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = 'attachment; filename=mydata.csv'

        return response

    @http.route('/stimula/1.0/tables/<string:table_name>', type='http', auth='none', methods=['POST'], csrf=False)
    @exception_handler
    @authentication_handler
    @connection_handler
    def post_table(self, table_name, **query):
        # header is optional
        header = query.get('h')

        # optional where clause parameter, fall back to all rows if none is provided
        where_clause = query.get('q')

        style = query.get('style')
        skiprows = int(query.get('skiprows', 0))
        assert style in ['diff', 'sql', 'result', 'full'], 'style must be one of diff, sql, result or full'
        insert = bool(eval(query.get('insert', 'false').capitalize()))
        update = bool(eval(query.get('update', 'false').capitalize()))
        delete = bool(eval(query.get('delete', 'false').capitalize()))
        execute = bool(eval(query.get('execute', 'false').capitalize()))
        commit = bool(eval(query.get('commit', 'false').capitalize()))
        context = query.get('context')
        body = request.httprequest.data.decode('utf-8')
        assert body, 'Missing body content'

        # if header is empty, then use the first row of the body as the header
        if not header:
            header = body.split('\n', 1)[0]

        if style == 'diff':
            # get diff, create sql and execute if requested and return three data frames separated by two newlines
            post_result = self._db.post_table_get_diff(table_name, header, where_clause, body, skiprows=skiprows, insert=insert, update=update, delete=delete, execute=execute, commit=commit)
            response_body = '\n\n'.join([df.to_csv(index=False) for df in post_result])
            # Set headers
            response = request.make_response(response_body)
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = 'attachment; filename=mydata.csv'
            return response

        if style == 'sql':
            # get diff, create sql, execute if requested and return a single data frame
            post_result = self._db.post_table_get_sql(table_name, header, where_clause, body, skiprows=skiprows, insert=insert, update=update, delete=delete, execute=execute, commit=commit)
            # convert df to response body, use double quotes where needed
            response_body = post_result.to_csv(index=False, quotechar="\"")
            # Set headers
            response = request.make_response(response_body)
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = 'attachment; filename=mydata.csv'
            return response

        if style == 'summary':
            # get diff, create sql, execute if requested and return a summary in json format
            post_result = self._db.post_table_get_summary(table_name, header, where_clause, body, skiprows=skiprows, insert=insert, update=update, delete=delete, execute=execute, commit=commit)
            # convert df to response body, use double quotes where needed
            response = request.make_response(post_result)
            return response

        if style == 'full':
            # get diff, create sql, execute if requested and return a full report in json format
            post_result = self._db.post_table_get_full_report(table_name, header, where_clause, body, skiprows=skiprows, insert=insert, update=update, delete=delete, execute=execute, commit=commit,
                                                              context=context)
            # create json response
            response = request.make_json_response(post_result)
            return response

        raise Exception(f'Invalid style parameter: {style}')

    @http.route('/stimula/1.0/tables', type='http', auth='none', methods=['POST'], csrf=False)
    @exception_handler
    @authentication_handler
    @connection_handler
    def post_tables(self, **query):
        tables = query.get('t')
        # header is optional
        header = query.get('h')

        insert = bool(eval(query.get('insert', 'false').capitalize()))
        update = bool(eval(query.get('update', 'false').capitalize()))
        delete = bool(eval(query.get('delete', 'false').capitalize()))
        execute = bool(eval(query.get('execute', 'false').capitalize()))
        commit = bool(eval(query.get('commit', 'false').capitalize()))

        # get files from multipart request body
        files = request.httprequest.files

        # get context names from filenames, exclude substitutions file
        context = [file.filename for file in files.values() if file.filename != 'substitutions.csv']

        # get contents from files, exclude substitutions file
        contents = [file.stream.read() for file in files.values() if file.filename != 'substitutions.csv']

        # get substitutions file if it exists
        substitutions_file = files.get('substitutions')
        substitutions = substitutions_file.stream.read() if substitutions_file else None

        # verify that table names were given for all files
        assert tables is not None, "Provide table names using the '-t' parameter"
        table_list = tables.split(',')
        assert tables is not None and len(table_list) == len(contents), "Provide exactly one file per table, not %s" % len(files)

        # get diff, create sql, execute if requested and return a full report in json format
        post_result = self._db.post_multiple_tables_get_full_report(table_list, header, None, contents, skiprows=1, insert=insert, update=update, delete=delete, execute=execute, commit=commit,
                                                                    context=context, substitutions=substitutions)
        # create json response
        response = request.make_json_response(post_result)
        return response
