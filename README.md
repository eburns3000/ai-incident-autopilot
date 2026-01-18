# Incident Autopilot

AI-Powered Incident Triage & Runbook Routing

## Overview

Incident Autopilot is a web-based application that automates the incident management process using AI to analyze, classify, and route incidents. The system provides intelligent triage capabilities with severity assessment, risk scoring, and recommended actions.

## Features

### Dashboard
- **Recent Incidents View**: Displays all recent incidents with key metadata
- **Real-time Status Updates**: Track incident status (triaged, overridden, resolved, approved)
- **Quick Actions**: Access triage, approve, override, resolve, and PIR generation functions directly from the dashboard
- **Severity Indicators**: Visual priority markers (P1, P2, P4) for quick assessment
- **Risk Scoring**: Percentage-based risk assessment for each incident

### Incident Management

#### Create New Incident
- **Title**: Descriptive incident name
- **Description**: Detailed incident information with prompts for context
- **Component**: Specify affected system component
- **Environment**: Select environment (e.g., prod, staging)
- **Reporter**: Track who reported the incident
- **Demo Data**: Quick-fill option for testing purposes

#### Incident Details View
Each incident displays:
- Unique ID
- Component and Environment
- Reporter information
- Creation timestamp
- Full description
- Current status (triaged, overridden, resolved, approved)

### AI Triage System

The AI Triage feature automatically analyzes incidents and provides:

#### Severity Classification
- **P1**: Critical priority incidents (e.g., security breaches)
- **P2**: High priority incidents (e.g., deployment issues, API errors)
- **P4**: Lower priority incidents (e.g., application issues)

#### Confidence Metrics
- AI confidence score (typically 85%)
- Risk score percentage (ranging from 45% to 75%)

#### Incident Categorization
- **Security**: Unauthorized access, breaches
- **Deployment**: Post-deployment issues
- **Application**: Frontend/application-related issues

#### Team Routing
- Automatic assignment to owner teams (e.g., data-platform, platform, engineering)
- Human review flag (Needs Human Review: TRUE/FALSE)

### Actions Available

#### Primary Actions
- **Run Triage**: Trigger AI analysis of the incident
- **Approve**: Accept the incident and recommendations
- **Override**: Manually adjust AI decisions
- **Resolve**: Mark incident as resolved
- **Generate PIR**: Create Post-Incident Review documentation

#### Audit Trail
- All actions (Approve/Override/Resolve) are logged in the audit trail
- Full transparency and accountability for incident handling

### Recommended Actions
The system provides intelligent recommendations based on the incident analysis, or indicates when no specific actions are recommended.

## Demo Mode

The application includes a demo-safe mode with:
- No authentication required
- Pre-populated test data
- Audit trail and PIR generation enabled
- Full feature access for evaluation

## Example Incidents

Based on the screenshots, here are typical incident types the system handles:

### 1. Security Breach
- **ID**: f4ec8554
- **Component**: db
- **Environment**: prod
- **Description**: Unauthorized access to database
- **Status**: overridden
- **Severity**: P1
- **Risk Score**: 75%
- **Owner Team**: data-platform

### 2. API Errors
- **ID**: 713385ac
- **Component**: checkout-api
- **Environment**: prod
- **Description**: The checkout API is returning 500 errors for about 30% of requests. Started 10 minutes ago after a deployment.
- **Status**: approved
- **Severity**: P2
- **Risk Score**: 65%
- **Type**: deployment
- **Owner Team**: platform

### 3. Test Incidents
- **ID**: 53bf2039
- **Component**: test-service
- **Environment**: prod
- **Description**: Testing the updated frontend
- **Status**: triaged
- **Severity**: P4
- **Risk Score**: 45%
- **Type**: application
- **Owner Team**: engineering

## Technical Details

- **Application URL**: localhost:8080
- **Interface**: Web-based UI with responsive design
- **Authentication**: Optional (can run in no-login mode)
- **Features**: Toggleable Demo-safe mode, Audit trail, PIR generation

## UI Navigation

### Header
- Application title: "Incident Autopilot"
- Subtitle: "AI-Powered Incident Triage & Runbook Routing"
- Mode indicators: Demo-safe, No login, Audit trail + PIR

### Main Navigation
- **Dashboard**: View all recent incidents
- **New Incident**: Create new incident reports

### Color Coding
- **Green (P4)**: Low priority
- **Yellow/Orange (P2)**: High priority
- **Red (P1)**: Critical priority

## User Interface Features

- Clean, modern design with blue gradient header
- Card-based incident display
- Action buttons prominently displayed
- Status badges for quick visual reference
- Refresh capability for real-time updates
- Back navigation for detailed views

## Workflow

1. **Incident Creation**: User reports incident with details
2. **AI Analysis**: System automatically triages upon creation or manual trigger
3. **Review**: Teams review AI recommendations and metrics
4. **Action**: Approve, override, or resolve based on assessment
5. **Documentation**: Generate PIR for closed incidents
6. **Audit**: All actions tracked in audit trail

## Benefits

- **Automated Triage**: Reduces manual effort in incident classification
- **Consistent Assessment**: AI provides objective severity and risk scoring
- **Faster Response**: Quick routing to appropriate teams
- **Audit Compliance**: Complete trail of all incident actions
- **Data-Driven**: Confidence and risk metrics support decision-making

---

*Note: This is a demo/development application running on localhost:8080

Complete. This version represents a finished end to end artifact.
