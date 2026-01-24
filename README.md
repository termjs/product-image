# Product Image Processor

A web application for standardizing product images with precision and consistency. Create templates from reference images and automatically process product photos to match exact specifications.

## Features

- **Template Creation**: Upload a reference product image to create a standardized template that captures dimensions and positioning
- **Image Processing**: Process product images to match template specifications automatically
- **Background Removal**: Automatically removes backgrounds and standardizes product positioning
- **Consistent Output**: Generates standardized 500x500px product images
- **Template Management**: Save and reuse multiple templates for different product categories

## Tech Stack

### Frontend

- Next.js 16.1.4
- React 19
- TypeScript
- Tailwind CSS 4
- Geist Font

### Backend

- Python Flask
- rembg (background removal)
- OpenCV (image processing)

## Prerequisites

- Node.js 20+ and pnpm
- Python 3.8+
- pip (Python package manager)

## Installation

### Frontend Setup

1. Install dependencies:

```bash
pnpm install
```

2. Start the development server:

```bash
pnpm dev
```

The frontend will be available at http://localhost:3000

### Backend Setup

1. Navigate to the backend directory:

```bash
cd backend
```

2. Install Python dependencies:

```bash
pip install flask flask-cors opencv-python rembg pillow numpy
```

3. Start the Flask server:

```bash
python app.py
```

The backend API will run on http://localhost:5000

## Usage

### Creating a Template

1. Navigate to the "Create Template" tab
2. Enter a template name
3. Upload a reference product image
4. Click "Create Template"

The system will process the image and create a reusable template.

### Processing Images

1. Navigate to the "Process Image" tab
2. Select a template from the dropdown
3. Upload a product image
4. Click "Process Image"

The processed image will be automatically downloaded as a standardized 500x500px PNG file.

## Project Structure

```
product-image/
├── app/                    # Next.js app directory
│   ├── page.tsx           # Main application component
│   ├── layout.tsx         # Root layout with metadata
│   └── globals.css        # Global styles and Tailwind config
├── backend/               # Python Flask backend
│   ├── app.py            # Flask API server
│   ├── templates.json    # Template storage
│   ├── output/           # Processed images
│   └── templates/        # Template files
├── public/               # Static assets
└── package.json          # Frontend dependencies
```

## API Endpoints

- `POST /create-template` - Create a new image template
- `POST /process` - Process an image using a template
- `GET /list-templates` - List all available templates
- `GET /get-trafaretas/<template_name>` - Get template preview
- `POST /cleanup` - Clean temporary files

## Development

### Frontend Development

```bash
pnpm dev
```

### Backend Development

```bash
cd backend
python app.py
```

### Building for Production

```bash
pnpm build
pnpm start
```
