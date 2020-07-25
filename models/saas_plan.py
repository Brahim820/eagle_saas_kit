# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Eagle IT Services (<https://eagle-erp.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://eagle-erp.com/>
#
#################################################################################
from urllib.parse import urlparse
from eagle import api, fields, models
from eagle.exceptions import UserError, Warning, ValidationError
from . lib import containers
from eagle.modules.module import get_module_resource
from eagle.models import NewId
from . lib import query
from . lib import saas
import logging
import time
import os
import docker
import base64
import re

_logger = logging.getLogger(__name__)

STATE = [
    ('draft', "Draft"),
    ('confirm', "Confirmed"),
    ('cancel', "Cancelled")
]

BILLING_CRITERIA = [
    ('fixed', "Fixed Rate"),
    ('per_user', 'Based on the No. of users')
]


class SaasPlans(models.Model):
    _name = "saas.plan"
    _order = "id desc"
    _description = 'Class for managing SaaS subscription plans.'

    @api.depends('name')
    def _compute_db_template_name(self):
        for obj in self:
            if obj.name and type(obj.id) != NewId and not obj.db_template:
                template_name = obj.name.lower().replace(" ", "_")
                obj.db_template = "{}_tid_{}".format(template_name, obj.id)

    def _default_saas_server(self):
        saas_servers = self.env['saas.server'].search([])
        if saas_servers:
            return saas_servers[0].id
        return False

    def _get_contract_count(self):
        for obj in self:
            contracts = self.env['saas.contract'].search(
                [('plan_id', '=', obj.id)])
            obj.contract_count = len(contracts)

    def action_view_contracts(self):
        contracts = self.env['saas.contract'].search(
            [('plan_id', '=', self.id)])

        action = self.env.ref('eagle_saas_kit.saas_contract_action').read()[0]
        if len(contracts) > 1:
            action['domain'] = [('id', 'in', contracts.ids)]
        elif len(contracts) == 1:
            action['views'] = [(self.env.ref(
                'eagle_saas_kit.saas_contract_form_view').id, 'form')]
            action['res_id'] = contracts.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    @api.onchange('server_id')
    def server_id_change(self):
        for obj in self:
            obj.saas_base_url = obj.server_id.server_domain

    name = fields.Char(string='Plan', required=True)
    saas_base_url = fields.Char(string="SaaS Domain(Base URL)", required=True)
    image = fields.Binary(string='Image')
    summary = fields.Char(string="Plan Summary")
    expiration = fields.Integer(
        'Expiration (hours)',
        help='time to delete database. Use for demo')
    grace_period = fields.Integer(
        'Grace period (days)', help='initial days before expiration')
    product_template_ids = fields.One2many(
        comodel_name="product.template",
        string="Linked Products",
        inverse_name="saas_plan_id")
    use_specific_user_template = fields.Boolean(
        string="Use Specific User Template", help="""Select if you want to provide some specific permissions to your user for acessing its eagle instance which is going to be created by this plan.""")
    template_user_id = fields.Char(string="Database Template User ID", help="""Enter the user_id of User which you have created in the DB Template with some specific permissions or whose permission you want to grant to the user of eagle instances which is going to be created by this plan.""")
    saas_module_ids = fields.Many2many(
        comodel_name="saas.module",
        relation="saas_plan_module_relation",
        column1="plan_id",
        column2="module_id",
        string="Related Modules")
    description = fields.Text('Plan Description')
    recurring_interval = fields.Integer(
        default=1, string='Default Billing Cycle')
    recurring_rule_type = fields.Selection(
        [('daily', 'Day(s)'),
         ('weekly', 'Week(s)'),
         ('monthly', 'Month(s)'),
         ('monthlylastday', 'Month(s) last day'),
         ('yearly', 'Year(s)'),
         ],
        default='monthly',
        string='Recurrence',
        readonly=True
    )
    # total_cycles = fields.Integer(string="Number of Cycles", default=1)
    trial_period = fields.Integer(string="Complimentary(Free) days", default=0)
    server_id = fields.Many2one(
        comodel_name="saas.server",
        string="SaaS Server",
        default=_default_saas_server,
        domain=[('state', '=', 'confirm')])
    db_template = fields.Char(
        compute='_compute_db_template_name', string="DB Template Name", store=True, help="Enter a uniquie name to create a DB associated to this plan or leave it blank and let eagle to give it a unique name.")
    container_id = fields.Char(string="Instance ID")
    state = fields.Selection(
        selection=STATE, string="States", default="draft")
    contract_count = fields.Integer(
        string='Contract Count', compute='_get_contract_count', readonly=True)
    billing_criteria = fields.Selection(
        selection=BILLING_CRITERIA,
        string="Default Billing Criteria",
        required=True,
        default="fixed")
    per_user_pricing = fields.Boolean(string="User Based Pricing", help="Used to enable the per user costing of end user's instance")
    user_cost = fields.Float(help="PUPC(Per User Per Cycle cost)")
    min_users = fields.Integer(string="Min. No. of user", help="Minimum number of users whose cost client have to pay either created or not", default="1")
    max_users = fields.Integer(string="Max. No. of user", help="End user is not allowed to create user more than Maximum number of user limit. Enter -1 to allow user to create infinte number of user.", default="1")
    due_users_price = fields.Float(string="Due users price", default="1.0")
    user_product = fields.Many2one(comodel_name="product.product", string="Product for user calculation", help="Select a product for calculation costing user pricing.", domain="[('is_user_pricing', '=', True)]") 

    @api.onchange('max_users')
    def check_max_user(self):
        for obj in self:
            if obj.max_users != -1 and obj.max_users < obj.min_users:
                raise UserError("Max. No. of users must be greater than or Equal to Min. no. of users")
            else:
                obj.max_users = obj.max_users

    @api.onchange('min_users')
    def check_min_users(self):
        for obj in self:
            if obj.min_users < 1:
                raise UserError("Min. No. of users can't be less than 1")
            if obj.min_users > obj.max_users:
                raise UserError("Max. No. of users must be greater than or Equal to Min. no. of users")

    def reset_to_draft(self):
        for obj in self:
            contracts = self.env['saas.contract'].search([('plan_id', '=', obj.id)])
            if contracts:
                raise UserError("This plan has some conracts associated with it!")
            obj.state = 'draft'

    def login_to_db_template(self):
        for obj in self:
            host_server, db_server = obj.server_id.get_server_details()
            response = query.get_credentials(
                obj.db_template,
                host_server=host_server,
                db_server=db_server)
            if response:
                login = response[0][0]
                password = response[0][1]
                login_url = "http://db13_templates.{}/saas/login?db={}&login={}&passwd={}".format(obj.saas_base_url,obj.db_template, login, password)

                _logger.info("$$$$$$$$$$$$$$%r", login_url)
                return {
                    'type': 'ir.actions.act_url',
                    'url': login_url,
                    'target': 'new',
                }
            else:
                raise UserError("Unknown Error!")

    def restart_db_template(self):
        for obj in self:
            host_server, db_server = obj.server_id.get_server_details()
            response_flag = containers.action(
                operation="restart",
                container_id=obj.container_id,
                host_server=host_server,
                db_server=db_server)
            if not response_flag:
                raise UserError("Operation Failed! Unknown Error!")

    def force_confirm(self):
        for obj in self:
            response = None
            if not obj.container_id:
                _, db_server = obj.server_id.get_server_details()
                response = query.is_db_exist(obj.db_template, db_server=db_server)
                if not response:
                    raise Warning("Please create DB Template First!")
            obj.state = 'confirm'

    def create_db_template(self):
        for obj in self:
            if not obj.db_template:
                raise UserError("Please select the DB template name first.")
            if re.match("^template_",obj.db_template):
                raise UserError("Couldn't Create DB. Please try again with some other Template Name!")
            db_template_name = "template_{}".format(obj.db_template)
            modules = [module.technical_name for module in obj.saas_module_ids]
            config_path = get_module_resource('eagle_saas_kit')
            modules.append('wk_saas_tool')
            try:
                host_server, db_server = obj.server_id.get_server_details()
                response = saas.create_db_template(
                    db_template=db_template_name,
                    modules=modules,
                    config_path=config_path,
                    host_server=host_server,
                    db_server=db_server)
            except Exception as e:
                _logger.info("--------DB-TEMPLATE-CREATION-EXCEPTION-------%r", e)
                raise UserError(e)
            else:
                if response:
                    if response.get('status', False):
                        obj.db_template = db_template_name
                        obj.state = 'confirm'
                        obj.container_id = response.get('container_id', False)
                    else:
                        msg = response.get('msg', False)
                        if msg:
                            raise UserError(msg)
                        else:
                            raise UserError("Unknown Error. Please try again later with some different Template Name")
                else:
                    raise UserError("No Response. Please try again later with some different Template Name")

    def unlink(self):
        for obj in self:
            if obj.contract_count:
                raise UserError("Error: You must delete the associated SaaS Contracts first!")
        return super(SaasPlans, self).unlink()

    @api.model
    def create(self, vals):
        if vals.get('recurring_interval', 0) <= 0:
            raise Warning("Default Billing Cycle can't be less than 1")
        res = super(SaasPlans, self).create(vals)
        for obj in res:
            if obj.name and not obj.db_template:
                template_name = obj.name.lower().replace(" ", "_")
                obj.db_template = "{}_tid_{}".format(template_name, res.id)
        return res

    def write(self, vals):
        if vals.get('recurring_interval', False) and vals['recurring_interval'] <= 0:
            raise Warning("Default Billing Cycle can't be less than 1")
        res = super(SaasPlans, self).write(vals)
        return res