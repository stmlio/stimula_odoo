import logging
import os
import traceback
from functools import wraps

from sqlalchemy import create_engine
from stimula.services.context import cnx_context
from stimula.services.db import DB

from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.modules.registry import Registry
from .odoo_auth import OdooAuth

_logger = logging.getLogger(__name__)
_auth = OdooAuth(os.environ.get('SECRET_KEY'))
_db = DB(None)


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
            error_status = 401 if isinstance(e, AccessDenied) else 400

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
        database, uid = _auth.validate_token(token)

        cnx_context.database = database
        cnx_context.uid = uid

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

    @http.route('/stimula/1.0/hello', type='http', auth='none', methods=['GET'], csrf=False)
    def hello(self):
        _logger.info('hello')
        return 'Hello world!!'

    @http.route('/stimula/1.0/auth', type='http', auth='none', methods=['POST'], csrf=False)
    @exception_handler
    def authenticate(self, **post):
        # authenticate the posted credentials. Always validate we can connect.
        token = _auth.authenticate(post['database'], post['username'], post['password'])

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
        tables = _db.get_tables(q_param)
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
            csv_header = _db.get_header_csv(table_name, h_param)
            response = request.make_response(csv_header)
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = 'attachment; filename=mydata.csv'
            return response

        json_header = _db.get_header_json(table_name, h_param)
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

        count = _db.get_count(table_name, h_param, q_param)
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
        csv_output = _db.get_table_as_csv(table_name, header, where_clause)

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
        assert style in ['diff', 'sql', 'result'], 'style must be one of diff, sql or result'
        insert = bool(eval(query.get('insert', 'false').capitalize()))
        update = bool(eval(query.get('update', 'false').capitalize()))
        delete = bool(eval(query.get('delete', 'false').capitalize()))
        execute = bool(eval(query.get('execute', 'false').capitalize()))
        commit = bool(eval(query.get('commit', 'false').capitalize()))
        body = request.httprequest.data.decode('utf-8')
        assert body, 'Missing body content'

        # if header is empty, then use the first row of the body as the header
        if not header:
            header = body.split('\n', 1)[0]

        if style == 'diff':
            # get diff, create sql and execute if requested and return three data frames separated by two newlines
            post_result = _db.post_table_get_diff(table_name, header, where_clause, body, skiprows=skiprows, insert=insert, update=update, delete=delete, execute=execute, commit=commit)
            response_body = '\n\n'.join([df.to_csv(index=False) for df in post_result])

        if style == 'sql':
            # get diff, create sql, execute if requested and return a single data frame
            post_result = _db.post_table_get_sql(table_name, header, where_clause, body, skiprows=skiprows, insert=insert, update=update, delete=delete, execute=execute, commit=commit)
            # convert df to response body, use double quotes where needed
            response_body = post_result.to_csv(index=False, quotechar="\"")

        if style == 'summary':
            # get diff, create sql, execute if requested and return a summary in json format
            post_result = _db.post_table_get_summary(table_name, header, where_clause, body, skiprows=skiprows, insert=insert, update=update, delete=delete, execute=execute, commit=commit)
            # convert df to response body, use double quotes where needed
            response_body = post_result

            # Create a response object with CSV data and appropriate headers

        # Create a response object with CSV data and appropriate headers
        response = request.make_response(response_body)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = 'attachment; filename=mydata.csv'

        return response
