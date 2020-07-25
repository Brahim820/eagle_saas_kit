# -*- coding: utf-8 -*-
#################################################################################
# Author      : Eagle IT Services (<https://eagle-erp.com/>)
# Copyright(c): 2015-Present Eagle IT Services
# All Rights Reserved.
# pip3 install paramiko
# pip3 install docker
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://eagle-erp.com/>
#################################################################################
{
  "name"                 :  "Eagle SaaS Kit",
  "summary"              :  "Eagle SaaS Kit allows you to run your Eagle As A SaaS business. After installation and set uo you can sell Eagle As A Saas to your client via subscription based model",
  "category"             :  "Extra Tools",
  "version"              :  "1.1.1",
  "sequence"             :  1,
  "author"               :  "Eagle IT Services",
  "website"              :  "https://www.eagle-erp.com/",
  "description"          :  """Provide Eagle as a Service(Saas) on your servers with Eagle saas Kit.""",
  "live_test_url"        :  "",
  "depends"              :  ['sale_management', 'portal', 'base', 'website_sale', 'account'],
  "data"                 :  [
                            'security/eagle_saas_kit_security.xml',
                            'security/ir.model.access.csv',
                            'views/res_config_views.xml',
                            'views/templates.xml',
                            'data/contract_sequence.xml',
                            'data/client_sequence.xml',
                            'data/email_templates.xml',
                            'data/contract_expiry_template.xml',
                            'views/subdomain_page.xml',
                            'data/recurring_invoice_cron.xml',
                            'data/client_creation_cron.xml',
                            'data/contract_expiry_cron.xml',
                            'views/saas_server_view.xml',
                            'views/module_category_view.xml',
                            'views/saas_plan_view.xml',
                            'views/module_view.xml',
                            'views/product_view.xml',
                            'views/account_invoice_view.xml',
                            'views/saas_contract_view.xml',
                            'views/saas_client_view.xml',
                            'views/sale_view.xml',
                            'views/saas_portal_templates.xml',
                            'views/user_pricing_template.xml',
                            'wizards/contract_creation_view.xml',
                            'views/menuitems.xml',
                            ],
  "images"               :  ['static/description/Banner.png'],
  "application"          :  True,
  "installable"          :  True,
  "auto_install"         :  False,
  "pre_init_hook"        :  "pre_init_check",
  "external_dependencies":  {'python': ['urllib']},
}
