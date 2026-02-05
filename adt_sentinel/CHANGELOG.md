# Changelog

All notable changes to the ADT Sentinel module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-04

### Added
- Initial release of ADT Sentinel module
- Model `adt.sentinel.report` for storing credit reports
- Wizard `adt.sentinel.query.wizard` for querying DNI
- Monthly validity control (1 report per DNI per month)
- Automatic state computation (vigente/vencido)
- Database constraint to prevent duplicates
- Protected fields (no modification after creation)
- Deletion protection (maintain full history)
- Tree, form, and search views
- 4 menu items for different report views
- Image storage in filestore (not in database)
- User traceability (who queried, when)
- Complete documentation (README, Security, Tests)
- Access control rules for users and admins
- Integration with Odoo chatter
- 25 documented test cases

### Security
- Input validation for DNI format (8 digits)
- SQL constraint for uniqueness (document + month + year)
- Double verification before creating report
- Protected fields cannot be modified
- Reports cannot be deleted (permanent history)
- Full audit trail with user and date

### Business Rules
- Only 1 report per DNI per month (cost saving)
- Automatic expiration when month changes
- Reuse of valid reports by all users
- S/ 10 cost warning on new queries
- Complete history maintained for audit

### Documentation
- README.md with full module description
- SECURITY_ARCHITECTURE.md with security details
- TEST_CASES.md with 25 test scenarios
- IMPLEMENTATION_SUMMARY.md with validation
- INSTALL.md with installation guide
- LICENSE (LGPL-3)
- CHANGELOG.md (this file)

### Technical
- Compatible with Odoo 15.0+
- Dependencies: base, contacts
- Python 3.7+
- PostgreSQL with unique constraints
- Computed stored fields for performance
- Searchable current_month helper field

## [Unreleased]

### Planned
- Rate limiting per user per day
- Email notifications for duplicate attempts
- Export reports with password protection
- Advanced audit dashboard
- Multi-company support
- Report expiration notifications
- Batch upload for multiple DNIs
- API endpoints for external integrations

---

## Version History

| Version | Date | Status | Notes |
|---------|------|--------|-------|
| 1.0.0 | 2026-02-04 | Released | Initial stable release |

---

## Migration Notes

### To 1.0.0
- Initial installation, no migration needed

---

## Breaking Changes

None (initial release)

---

## Deprecation Warnings

- File `views/sentinel_views.xml` is obsolete but maintained for compatibility
- Will be removed in version 2.0.0

---

**Maintained by:** ADT Development Team  
**Last Updated:** February 4, 2026
