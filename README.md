# FixHR GPT Local - AI-Powered HR Management System

A comprehensive Django-based HR management system with AI-powered command generation using fine-tuned language models.

## 🚀 Features

### Core Functionality
- **AI-Powered Command Generation**: Uses fine-tuned Falcon-7B model for natural language processing
- **FixHR API Integration**: Seamless integration with FixHR APIs for real-time data
- **Multi-language Support**: English and Hindi support for user interactions
- **Role-based Access**: Different permissions for employees and administrators

### HR Operations
- **Leave Management**: Apply, view, and approve leave requests
- **Attendance Tracking**: View attendance reports and analytics
- **Gatepass Management**: Apply and approve gatepass requests
- **Missed Punch**: Submit and manage missed punch requests
- **Holiday Management**: View holiday lists and check holiday status
- **Approval Workflows**: Streamlined approval processes for all requests

### AI Capabilities
- **Natural Language Processing**: Understand user intent from natural language
- **Command Extraction**: Automatically extract commands from user queries
- **Context Awareness**: Maintains context across conversations
- **Fallback System**: Rule-based fallback when AI model is unavailable

## 📁 Project Structure

```
fixhr_gpt_local/
├── core/                          # Django app
│   ├── models.py                  # Database models
│   ├── views.py                   # Main application logic
│   ├── urls.py                    # URL routing
│   ├── train_model.py             # Model training script
│   ├── model_inference.py         # Model inference system
│   └── templates/                 # HTML templates
│       ├── login_page.html
│       └── chat_page.html
├── dataset/                       # Training data
│   ├── general_data.json          # General HR instructions
│   ├── fix_hr_data.json          # FixHR-specific commands
│   ├── attendance_data.json       # Sample attendance data
│   ├── leaves_data.json          # Sample leave data
│   ├── gatepass_data.json        # Sample gatepass data
│   ├── holidays_data.json        # Sample holiday data
│   └── missed_punch_data.json    # Sample missed punch data
├── fixhr_gpt_local/              # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── manage_model.py               # Model management script
├── manage.py                     # Django management
└── requirements.txt              # Python dependencies
```

## 🛠️ Installation

### Prerequisites
- Python 3.8+
- CUDA-compatible GPU (recommended for training)
- 8GB+ RAM
- 10GB+ free disk space

### Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd fixhr_gpt_local
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Install additional ML dependencies**
```bash
pip install torch transformers datasets peft accelerate bitsandbytes
```

5. **Run migrations**
```bash
python manage.py migrate
```

6. **Create superuser (optional)**
```bash
python manage.py createsuperuser
```

## 🎯 Usage

### Starting the Application

1. **Run Django server**
```bash
python manage.py runserver
```

2. **Access the application**
- Open browser to `http://localhost:8000`
- Login with your FixHR credentials

### Model Management

#### Check System Status
```bash
python manage_model.py check
```

#### Train the Model
```bash
python manage_model.py train
```

#### Test the Model
```bash
python manage_model.py test
```

#### Check Model Status
```bash
python manage_model.py status
```

### API Endpoints

#### Authentication
- `POST /login/api/` - User login
- `GET /logout/` - User logout

#### Chat & AI
- `POST /api/chat/` - Main chat interface with AI
- `GET /api/model-status/` - Check model availability
- `POST /api/load-model/` - Load AI model
- `POST /api/train-model/` - Train AI model

## 💬 Usage Examples

### Natural Language Commands

**Leave Management:**
- "I need to apply for leave tomorrow for personal work"
- "Show me my leave balance"
- "What are my pending leave requests?"

**Attendance:**
- "Show me attendance report for October 2025"
- "Who was absent yesterday?"
- "Show employees who came after 10am today"

**Holidays:**
- "Is today a holiday?"
- "What's the next holiday?"
- "Show me holidays for December 2025"

**Gatepass:**
- "Apply gatepass for 10am to 11am for meeting"
- "Show pending gatepass approvals"

**Missed Punch:**
- "Apply missed punch for today in 9am out 6pm for forgot"
- "Show my missed punch requests"

### Direct Commands

**Leave:**
- `apply leave for 15-17 December 2025 for family function`
- `my leave balance`
- `pending leave`

**Attendance:**
- `attendance report for October 2025`
- `absent report for 20 October 2025`

**Holidays:**
- `today holiday`
- `next holiday`
- `holiday list for October 2025`

## 🔧 Configuration

### Model Configuration
Edit `core/train_model.py` to modify:
- Model architecture
- Training parameters
- Data preprocessing
- Output settings

### API Configuration
Edit `core/views.py` to modify:
- FixHR API endpoints
- Authentication settings
- Response formatting

### Training Data
- Add new training examples to `dataset/general_data.json`
- Format: `{"instruction": "user query", "output": "expected response"}`

## 🧠 AI Model Details

### Architecture
- **Base Model**: Falcon-7B-Instruct
- **Fine-tuning**: LoRA (Low-Rank Adaptation)
- **Quantization**: 4-bit quantization (optional)
- **Training**: Supervised fine-tuning on HR domain data

### Training Process
1. **Data Preparation**: Convert JSON training data to model format
2. **Tokenization**: Process text using Falcon tokenizer
3. **LoRA Setup**: Configure low-rank adaptation parameters
4. **Training**: Fine-tune on HR-specific data
5. **Inference**: Generate responses for user queries

### Performance
- **Training Time**: ~2-4 hours on RTX 3080
- **Inference Speed**: ~1-2 seconds per query
- **Memory Usage**: ~8GB VRAM for training, ~4GB for inference
- **Accuracy**: High accuracy on HR domain tasks

## 🔒 Security

- **Authentication**: Session-based authentication
- **API Security**: CSRF protection on sensitive endpoints
- **Data Privacy**: Local model processing (no external API calls)
- **Access Control**: Role-based permissions

## 🐛 Troubleshooting

### Common Issues

**Model Training Fails:**
- Check CUDA availability: `python -c "import torch; print(torch.cuda.is_available())"`
- Verify data files exist and are properly formatted
- Ensure sufficient disk space and memory

**Model Loading Fails:**
- Check if model files exist in `fixhr_model/` directory
- Verify model compatibility with current transformers version
- Try retraining the model

**API Errors:**
- Check FixHR API connectivity
- Verify authentication tokens
- Check Django logs for detailed error messages

**Performance Issues:**
- Use GPU acceleration for better performance
- Reduce model size or use quantization
- Optimize batch sizes and sequence lengths

### Debug Mode
Enable debug logging by setting in `settings.py`:
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'core': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

## 📈 Performance Optimization

### Training Optimization
- Use mixed precision training (fp16/bf16)
- Enable gradient checkpointing
- Use data parallelism for multi-GPU setups
- Optimize batch sizes based on GPU memory

### Inference Optimization
- Use model quantization (4-bit/8-bit)
- Enable model caching
- Implement response caching
- Use batch processing for multiple queries

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- FixHR for providing the API access
- Hugging Face for the transformers library
- Falcon model team for the base model
- Django community for the web framework

## 📞 Support

For support and questions:
- Create an issue in the repository
- Check the troubleshooting section
- Review the documentation

---

**Note**: This system is designed for educational and development purposes. Ensure proper testing before deploying to production environments.
