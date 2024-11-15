# -*- coding: utf-8 -*-
# Copyright 2023-Today TechKhedut.
# Part of TechKhedut. See LICENSE file for full copyright and licensing details.
import base64
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError
from odoo.addons.web_editor.tools import get_video_embed_code, get_video_thumbnail


class LandLordPartner(models.Model):

    _name = "landlord.partner"

    project_id = fields.Many2one('property.project')
    partner_id = fields.Many2one('res.partner',domain="[('user_type','=','landlord')]")
    ownership = fields.Integer()

