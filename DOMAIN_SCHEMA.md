# Domain Schema: Grocery Recall Notice

This schema was defined before implementing the HTML form or agent workflow.

## Assigned domain

- `DOMAIN_ID`: 3
- Assigned domain: Grocery supply and recall notices
- Entity: Grocery Recall Notice

## Entity fields

| Field | HTML name | Type | Required | Validation and purpose |
| --- | --- | --- | --- | --- |
| Product name | `productName` | Text | Yes | Primary field; identifies the affected grocery product. |
| Brand name | `brandName` | Text | Yes | Secondary field; identifies the product brand or supplier. |
| Submitter email | `submitterEmail` | Email | Yes | Contact address for the person submitting the notice. |
| Notice description | `description` | Text area | Yes | Explains the recall or supply notice; must contain more than 25 characters. |
| Notice category | `category` | Select | Yes | Classifies the notice using one of the four values below. |
| Terms accepted | `termsAccepted` | Checkbox | Yes | Confirms agreement to the terms and conditions. |
| Submission date | `submissionDate` | ISO 8601 string | Generated | Added in JavaScript after successful validation. |

## Category values

| Stored value | Display label | Intended use |
| --- | --- | --- |
| `food-safety-recall` | Food Safety Recall | Contamination, spoilage, or another direct food-safety issue. |
| `allergen-alert` | Allergen Alert | Missing or incorrect allergen declarations. |
| `quality-withdrawal` | Quality Withdrawal | Non-safety defects that require a product withdrawal. |
| `supply-shortage` | Supply Shortage | Availability interruptions or grocery supply constraints. |

## Fixed personal configuration

| Value | Result |
| --- | ---: |
| `SID4` | 9619 |
| `PORT_BASE` | 8619 |
| `PREFIX` | `s9619` |
| `SEED` | 9619 |
| `VERIFY_SEED` | 269619 |
| `DOMAIN_ID` | 3 |
