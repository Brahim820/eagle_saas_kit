# -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2016-Present Eagle IT Services (<https://eagle-erp.com/>)
#   See LICENSE file for full copyright and licensing details.
#   License URL : <https://eagle-erp.com/>
# 
#################################################################################

from eagle import fields, models

class AccountInvoice(models.Model):
    _inherit = 'account.move'

    contract_id = fields.Many2one(comodel_name='saas.contract', string='SaaS Contract')