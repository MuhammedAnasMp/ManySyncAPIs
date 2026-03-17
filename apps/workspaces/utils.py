from firebase_admin import firestore

def send_invitation_email(email, workspace_name, invited_by_name):
    """
    Sends an invitation email using the Firebase 'Trigger Email from Firestore' extension pattern.
    It creates a document in the 'mail' collection which triggers the email.
    """
    db = firestore.client()
    
    mail_data = {
        'to': email,
        'message': {
            'subject': f'Invitation to join {workspace_name} on Iggram',
            'html': f'''
                <div style="font-family: sans-serif; padding: 20px; color: #333;">
                    <h2 style="color: #6366f1;">You've been invited!</h2>
                    <p>Hello,</p>
                    <p><strong>{invited_by_name}</strong> has invited you to collaborate on the workspace <strong>{workspace_name}</strong> on Iggram.</p>
                    <p>Iggram is a powerful social media management platform that helps you grow your brand.</p>
                    <div style="margin: 30px 0;">
                        <a href="http://localhost:5174/signup?email={email}" 
                           style="background-color: #6366f1; color: white; padding: 12px 24px; text-decoration: none; rounded: 8px; font-weight: bold;">
                            Accept Invitation & Sign Up
                        </a>
                    </div>
                    <p style="font-size: 12px; color: #666;">If you didn't expect this invitation, you can safely ignore this email.</p>
                </div>
            '''
        }
    }
    
    # Add to 'mail' collection to trigger the extension
    db.collection('mail').add(mail_data)
    print(f"Invitation email triggered for {email}")
