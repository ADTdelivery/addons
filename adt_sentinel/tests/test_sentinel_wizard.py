# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError
from odoo import fields
import base64


class TestSentinelWizard(TransactionCase):
    """Test cases for adt.sentinel.query.wizard"""

    def setUp(self):
        super(TestSentinelWizard, self).setUp()
        self.SentinelReport = self.env['adt.sentinel.report']
        self.SentinelWizard = self.env['adt.sentinel.query.wizard']

        # Create fake image data
        self.fake_image = base64.b64encode(b'fake image content')

    def test_01_wizard_search_not_found(self):
        """Test wizard search with non-existent DNI"""
        wizard = self.SentinelWizard.create({
            'document_number': '12345678',
        })

        wizard.action_search()

        self.assertEqual(wizard.state, 'not_found')
        self.assertFalse(wizard.found_report_id)

    def test_02_wizard_search_found(self):
        """Test wizard search with existing report"""
        # Create report first
        report = self.SentinelReport.create({
            'document_number': '87654321',
            'report_image': self.fake_image,
            'query_date': fields.Date.today(),
        })

        # Search with wizard
        wizard = self.SentinelWizard.create({
            'document_number': '87654321',
        })

        wizard.action_search()

        self.assertEqual(wizard.state, 'found')
        self.assertEqual(wizard.found_report_id.id, report.id)

    def test_03_wizard_invalid_dni(self):
        """Test wizard validation with invalid DNI"""
        with self.assertRaises(ValidationError):
            wizard = self.SentinelWizard.create({
                'document_number': '1234567',  # 7 digits
            })
            wizard.action_search()

    def test_04_wizard_upload_without_image(self):
        """Test upload without image raises error"""
        wizard = self.SentinelWizard.create({
            'document_number': '11223344',
        })
        wizard.action_search()

        # Try to upload without image
        with self.assertRaises(UserError):
            wizard.action_upload_report()

    def test_05_wizard_upload_success(self):
        """Test successful report upload"""
        wizard = self.SentinelWizard.create({
            'document_number': '99887766',
        })
        wizard.action_search()

        self.assertEqual(wizard.state, 'not_found')

        # Upload image
        wizard.write({
            'new_report_image': self.fake_image,
            'notes': 'Test upload',
        })

        result = wizard.action_upload_report()

        # Verify report was created
        report = self.SentinelReport.search([
            ('document_number', '=', '99887766')
        ])

        self.assertTrue(report)
        self.assertEqual(report.document_number, '99887766')
        self.assertEqual(report.notes, 'Test upload')

    def test_06_wizard_duplicate_detection(self):
        """Test wizard detects duplicates even in race condition"""
        wizard1 = self.SentinelWizard.create({
            'document_number': '55667788',
        })
        wizard1.action_search()

        wizard2 = self.SentinelWizard.create({
            'document_number': '55667788',
        })
        wizard2.action_search()

        # First wizard uploads
        wizard1.write({'new_report_image': self.fake_image})
        wizard1.action_upload_report()

        # Second wizard tries to upload
        wizard2.write({'new_report_image': self.fake_image})
        with self.assertRaises(UserError):
            wizard2.action_upload_report()

    def test_07_wizard_validity_message(self):
        """Test validity message computation"""
        # Create report
        report = self.SentinelReport.create({
            'document_number': '44332211',
            'report_image': self.fake_image,
            'query_date': fields.Date.today(),
        })

        # Create wizard and search
        wizard = self.SentinelWizard.create({
            'document_number': '44332211',
        })
        wizard.action_search()

        self.assertEqual(wizard.state, 'found')
        self.assertTrue(wizard.validity_message)
        self.assertIn('Reporte Encontrado', wizard.validity_message)
        self.assertIn('VIGENTE', wizard.validity_message)
