# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError
from odoo import fields
import base64


class TestSentinelReport(TransactionCase):
    """Test cases for adt.sentinel.report model"""

    def setUp(self):
        super(TestSentinelReport, self).setUp()
        self.SentinelReport = self.env['adt.sentinel.report']

        # Create fake image data
        self.fake_image = base64.b64encode(b'fake image content')

    def test_01_create_report(self):
        """Test creating a valid report"""
        report = self.SentinelReport.create({
            'document_number': '12345678',
            'report_image': self.fake_image,
            'query_date': fields.Date.today(),
        })

        self.assertTrue(report.id)
        self.assertEqual(report.document_number, '12345678')
        self.assertEqual(report.state, 'vigente')
        self.assertTrue(report.is_current_month)

    def test_02_invalid_dni_length(self):
        """Test validation: DNI must be 8 digits"""
        with self.assertRaises(ValidationError):
            self.SentinelReport.create({
                'document_number': '1234567',  # 7 digits
                'report_image': self.fake_image,
                'query_date': fields.Date.today(),
            })

    def test_03_invalid_dni_format(self):
        """Test validation: DNI must be numeric"""
        with self.assertRaises(ValidationError):
            self.SentinelReport.create({
                'document_number': '1234567a',  # Contains letter
                'report_image': self.fake_image,
                'query_date': fields.Date.today(),
            })

    def test_04_unique_constraint(self):
        """Test constraint: Only 1 report per DNI per month"""
        # Create first report
        self.SentinelReport.create({
            'document_number': '87654321',
            'report_image': self.fake_image,
            'query_date': fields.Date.today(),
        })

        # Try to create duplicate
        with self.assertRaises(Exception):  # IntegrityError or ValidationError
            self.SentinelReport.create({
                'document_number': '87654321',
                'report_image': self.fake_image,
                'query_date': fields.Date.today(),
            })

    def test_05_search_current_report(self):
        """Test search_current_report method"""
        # Create report
        report = self.SentinelReport.create({
            'document_number': '11223344',
            'report_image': self.fake_image,
            'query_date': fields.Date.today(),
        })

        # Search
        found = self.SentinelReport.search_current_report('11223344')

        self.assertEqual(found.id, report.id)
        self.assertTrue(found.is_current_month)

    def test_06_cannot_delete(self):
        """Test that reports cannot be deleted"""
        report = self.SentinelReport.create({
            'document_number': '99887766',
            'report_image': self.fake_image,
            'query_date': fields.Date.today(),
        })

        with self.assertRaises(UserError):
            report.unlink()

    def test_07_cannot_modify_protected_fields(self):
        """Test that protected fields cannot be modified"""
        report = self.SentinelReport.create({
            'document_number': '55667788',
            'report_image': self.fake_image,
            'query_date': fields.Date.today(),
        })

        # Try to modify document_number
        with self.assertRaises(UserError):
            report.write({'document_number': '11111111'})

        # Try to modify image
        with self.assertRaises(UserError):
            report.write({'report_image': base64.b64encode(b'new image')})

    def test_08_can_modify_notes(self):
        """Test that notes field can be modified"""
        report = self.SentinelReport.create({
            'document_number': '44332211',
            'report_image': self.fake_image,
            'query_date': fields.Date.today(),
            'notes': 'Initial note',
        })

        # This should work
        report.write({'notes': 'Updated note'})
        self.assertEqual(report.notes, 'Updated note')

    def test_09_computed_fields(self):
        """Test that computed fields are calculated correctly"""
        today = fields.Date.today()
        report = self.SentinelReport.create({
            'document_number': '22334455',
            'report_image': self.fake_image,
            'query_date': today,
        })

        self.assertEqual(report.query_month, today.month)
        self.assertEqual(report.query_year, today.year)
        self.assertEqual(report.state, 'vigente')
        self.assertTrue(report.is_current_month)

    def test_10_name_get(self):
        """Test display name format"""
        report = self.SentinelReport.create({
            'document_number': '66778899',
            'report_image': self.fake_image,
            'query_date': fields.Date.today(),
        })

        name = report.name_get()[0][1]
        self.assertIn('66778899', name)
        self.assertIn('✅', name)  # Vigente icon
