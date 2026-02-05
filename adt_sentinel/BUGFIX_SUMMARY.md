# Bug Fix Summary - ADT Sentinel Module

## Date: February 4, 2026

## Error Description (Multiple Issues)

### Issue 1: Initial Installation Error
```
ValidationError: Invalid view adt.sentinel.report.tree definition in adt_sentinel/views/sentinel_report_views.xml
ParseError: while parsing /mnt/extra-addons/adt_sentinel/views/sentinel_report_views.xml:7
```

### Issue 2: Wizard View Expression Error  
```
NameError: name 'new_report_image' is not defined
ValueError: <class 'NameError'>: "name 'new_report_image' is not defined" while evaluating 'new_report_image == False'
ParseError: while parsing /mnt/extra-addons/adt_sentinel/wizard/sentinel_query_wizard_views.xml:118
```

## Root Causes Identified

### 1. **Invalid Tree View Definition**
- **Issue**: The `state` field in the tree view had both `widget="badge"` and field-level `decoration-*` attributes
- **Problem**: In Odoo, decoration attributes (`decoration-success`, `decoration-secondary`) should only be used at the tree element level, NOT on individual fields when using the badge widget
- **Location**: `views/sentinel_report_views.xml`, lines 20-23

### 2. **Missing Mail/Chatter Dependencies**
- **Issue**: The form view included chatter fields (`message_follower_ids`, `message_ids`) but the model didn't inherit from `mail.thread`
- **Problem**: This causes validation errors when Odoo tries to load the view
- **Location**: `views/sentinel_report_views.xml`, form view

### 3. **Invalid Expression in Invisible Attribute (Critical)**
- **Issue**: Wizard view used `invisible="new_report_image == False"` on a field that appears twice in the form
- **Problem**: The expression context cannot evaluate field references in this way when the same field is used multiple times (once as binary widget, once as image widget)
- **Location**: `wizard/sentinel_query_wizard_views.xml`, line 168

### 4. **Incorrect Invisible Syntax for Non-Field Elements**
- **Issue**: Using simple expressions like `invisible="state != 'vigente'"` on `<span>` elements
- **Problem**: Non-field elements need to use the `attrs` syntax with domain notation
- **Location**: `views/sentinel_report_views.xml`, form view spans

## Changes Made

### File: `views/sentinel_report_views.xml`

#### Change 1: Fixed Tree View (Lines 11-25)
**Before:**
```xml
<field name="state"
       widget="badge"
       decoration-success="state == 'vigente'"
       decoration-secondary="state == 'vencido'"/>
```

**After:**
```xml
<field name="state" widget="badge"/>
```

**Reason**: Removed conflicting decoration attributes from field level. The tree-level decorations are sufficient.

#### Change 2: Removed Chatter Section (Form View)
**Before:**
```xml
</sheet>
<div class="oe_chatter">
    <field name="message_follower_ids" widget="mail_followers"/>
    <field name="message_ids" widget="mail_thread"/>
</div>
```

**After:**
```xml
</sheet>
```

**Reason**: Model doesn't inherit from `mail.thread`, so these fields don't exist.

#### Change 3: Fixed Invisible Syntax on Span Elements (Form View)
**Before:**
```xml
<span invisible="state != 'vigente'">
```

**After:**
```xml
<span attrs="{'invisible': [('state', '!=', 'vigente')]}">
```

**Reason**: Non-field elements require attrs domain syntax, not simple expressions.

### File: `wizard/sentinel_query_wizard_views.xml`

#### Change 1: Removed Invalid Invisible Expression
**Before:**
```xml
<field name="new_report_image"
       widget="image"
       nolabel="1"
       invisible="new_report_image == False"
       options="{'size': [600, 0]}"/>
```

**After:**
```xml
<field name="new_report_image"
       widget="image"
       nolabel="1"
       options="{'size': [600, 0]}"/>
```

**Reason**: 
1. The field appears twice in the form (binary and image widgets)
2. The expression `new_report_image == False` cannot be evaluated in the view context
3. The image widget naturally handles empty values by displaying nothing, so conditional visibility is unnecessary

## Testing Recommendations

1. **Install the module** in a test database:
   ```bash
   odoo-bin -d test_db -u adt_sentinel
   ```

2. **Verify tree view renders correctly** with proper state badges

3. **Verify form view opens** without errors

4. **Test the wizard workflow**:
   - Open "Consultar DNI"
   - Search for a DNI
   - Verify the upload form works

5. **Check menu items** are all accessible

## Additional Notes

### If Mail/Chatter is Needed Later
To add chatter functionality:

1. Update the model (`models/sentinel.py`):
```python
class SentinelReport(models.Model):
    _name = 'adt.sentinel.report'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Reporte Crediticio Sentinel'
```

2. Add dependency in `__manifest__.py`:
```python
"depends": ["base", "contacts", "mail"],
```

3. Add tracking to fields:
```python
state = fields.Selection(
    ...,
    tracking=True  # Track changes in chatter
)
```

### Decoration Color Options
Valid decoration attributes for tree views:
- `decoration-bf` (bold)
- `decoration-it` (italic)
- `decoration-danger` (red)
- `decoration-info` (blue)
- `decoration-muted` (gray)
- `decoration-primary` (primary color)
- `decoration-success` (green)
- `decoration-warning` (orange)

## Status
✅ **Fixed** - Module should now install without errors
