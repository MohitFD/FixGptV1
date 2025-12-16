# FixHR Comprehensive Training Dataset Documentation

## 📊 Dataset Overview

The comprehensive training dataset (`comprehensive_training_data.json`) is a merged collection of all HR-related training data from multiple sources, organized with proper categorization and metadata for effective AI model training.

### 📈 Statistics
- **Total Examples**: 74 training examples
- **Languages**: English (64 examples) + Hindi (10 examples)
- **Categories**: 7 distinct HR modules
- **Data Quality**: 100% valid examples with no duplicates

## 🗂️ Dataset Structure

```json
{
  "metadata": {
    "description": "Comprehensive FixHR Training Dataset - Merged from all HR modules",
    "total_examples": 74,
    "categories": {
      "general_hr": "General HR app usage and installation",
      "leave_management": "Leave application, balance, approvals",
      "attendance_tracking": "Attendance reports, analysis, time filters",
      "gatepass_management": "Gatepass application and approvals",
      "holiday_management": "Holiday queries and information",
      "missed_punch": "Missed punch application and management",
      "approval_workflows": "Approval and rejection processes"
    },
    "languages": ["English", "Hindi"],
    "created_date": "2025-01-09"
  },
  "train": [
    {
      "instruction": "User query or command",
      "output": "Expected response or action",
      "category": "Module category",
      "language": "Language used"
    }
  ]
}
```

## 📂 Category Breakdown

### 1. General HR (20 examples - 27.0%)
**Purpose**: Basic app usage, installation, and general HR features
- App installation (Android/iOS)
- Login procedures
- Basic navigation
- Profile management
- Password recovery
- Troubleshooting

**Example Commands**:
- "How to install Fix HR app?"
- "How to login in Fix HR app?"
- "What is Fix HR?"

### 2. Holiday Management (12 examples - 16.2%)
**Purpose**: Holiday queries and information retrieval
- Today's holiday check
- Tomorrow's holiday check
- Next/previous holiday
- Monthly/yearly holiday lists
- Holiday calendar views

**Example Commands**:
- "today holiday"
- "Show holidays for October 2025"
- "next holiday"

### 3. Leave Management (11 examples - 14.9%)
**Purpose**: Leave application and management
- Leave application process
- Leave balance checking
- Leave request viewing
- Leave type explanations

**Example Commands**:
- "How do I apply for leave?"
- "What is my leave balance?"
- "apply leave for tomorrow for personal work"

### 4. Attendance Tracking (10 examples - 13.5%)
**Purpose**: Attendance reports and analysis
- Attendance reports
- Employee presence checking
- Late/absent analysis
- Time-based filtering
- Attendance analytics

**Example Commands**:
- "Show attendance report for October 2025"
- "Is John present today?"
- "Show late employees for 15 October 2025"

### 5. Missed Punch (8 examples - 10.8%)
**Purpose**: Missed punch application and management
- Missed punch application
- Punch type selection
- Reason categorization
- Request tracking

**Example Commands**:
- "How do I apply for missed punch?"
- "apply missed punch for today in 9am out 6pm for forgot"
- "Show my missed punch requests"

### 6. Gatepass Management (7 examples - 9.5%)
**Purpose**: Gatepass application and approvals
- Gatepass application
- Time and destination specification
- Approval workflows
- Request tracking

**Example Commands**:
- "How do I apply for gatepass?"
- "apply gatepass for 10am to 11am for meeting"
- "Show pending gatepass approvals"

### 7. Approval Workflows (6 examples - 8.1%)
**Purpose**: Approval and rejection processes
- Leave approvals/rejections
- Gatepass approvals/rejections
- Missed punch approvals/rejections
- Command format explanations

**Example Commands**:
- "How do I approve leave requests?"
- "How do I reject gatepass requests?"
- "approve leave|LEAVE_ID|EMP_D_ID|MODULE_ID|MASTER_MODULE_ID|note"

## 🌐 Language Support

### English (64 examples - 86.5%)
- Primary language for all HR operations
- Complete coverage of all modules
- Formal business language
- Technical terminology

### Hindi (10 examples - 13.5%)
- Localized commands for Indian users
- Common HR operations
- Informal conversational style
- Cultural context integration

## 📏 Data Quality Metrics

### Instruction Length
- **Average**: 32.9 characters
- **Range**: 12-62 characters
- **Quality**: Concise and clear commands

### Output Length
- **Average**: 197.8 characters
- **Range**: 25-562 characters
- **Quality**: Detailed and informative responses

### Validation Results
- ✅ **100% Valid Examples**: All examples pass validation
- ✅ **No Duplicates**: Unique instruction set
- ✅ **Proper Structure**: Consistent JSON format
- ✅ **Complete Fields**: All required fields present

## 🎯 Training Objectives

### 1. Command Recognition
Train the model to recognize various HR-related commands and queries:
- Direct commands: "apply leave for tomorrow"
- Questions: "How do I check my leave balance?"
- Natural language: "I need to apply for leave tomorrow"

### 2. Intent Classification
Classify user intents into appropriate HR modules:
- Leave management
- Attendance tracking
- Holiday queries
- Gatepass requests
- Missed punch applications

### 3. Response Generation
Generate appropriate responses based on:
- User role (Employee/Manager)
- Available data
- System capabilities
- Context understanding

### 4. Multi-language Support
Handle both English and Hindi queries with:
- Language detection
- Appropriate response language
- Cultural context awareness

## 🔄 Data Sources

The comprehensive dataset merges data from:

1. **general_data.json** - General HR app usage (636 examples)
2. **fix_hr_data.json** - FixHR-specific commands (93 examples)
3. **leaves_data.json** - Leave management (41 examples)
4. **attendance_data.json** - Attendance tracking (41 examples)
5. **gatepass_data.json** - Gatepass management (37 examples)
6. **holidays_data.json** - Holiday information (49 examples)
7. **missed_punch_data.json** - Missed punch handling (41 examples)

## 🚀 Usage Instructions

### For Training
```bash
# Use the comprehensive dataset for training
python core/train_model.py
```

### For Validation
```bash
# Validate the dataset
python validate_training_data.py
```

### For Analysis
```python
import json

# Load and analyze the dataset
with open('dataset/comprehensive_training_data.json', 'r') as f:
    data = json.load(f)

# Access training examples
examples = data['train']
print(f"Total examples: {len(examples)}")

# Filter by category
leave_examples = [ex for ex in examples if ex.get('category') == 'leave_management']
print(f"Leave management examples: {len(leave_examples)}")
```

## 📝 Adding New Examples

When adding new training examples, follow this format:

```json
{
  "instruction": "Clear, specific user query",
  "output": "Detailed, helpful response",
  "category": "appropriate_category",
  "language": "English_or_Hindi"
}
```

### Guidelines:
1. **Instructions**: Be specific and realistic
2. **Outputs**: Provide complete, actionable responses
3. **Categories**: Use existing categories or add new ones
4. **Languages**: Maintain language consistency
5. **Quality**: Ensure examples are unique and valuable

## 🔧 Maintenance

### Regular Tasks:
1. **Validation**: Run validation script after changes
2. **Quality Check**: Review new examples for consistency
3. **Balance**: Maintain category and language balance
4. **Updates**: Keep examples current with system changes

### Version Control:
- Track changes to training data
- Maintain backup of previous versions
- Document significant updates
- Test model performance after changes

## 📊 Performance Metrics

### Expected Improvements:
- **Command Recognition**: 95%+ accuracy
- **Intent Classification**: 90%+ accuracy
- **Response Quality**: High user satisfaction
- **Multi-language**: Seamless language switching

### Monitoring:
- Track model performance on test data
- Monitor user feedback and satisfaction
- Analyze common failure cases
- Update training data based on insights

---

**Last Updated**: January 9, 2025
**Version**: 1.0
**Status**: Production Ready
