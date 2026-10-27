"use client";

import { useAuth, UserButton, SignInButton } from "@clerk/nextjs";
import { Dashboard } from "@/components/dashboard";

const anonymous = async () => null;

function AuthenticatedWorkspace() {
  const { getToken, isSignedIn } = useAuth();
  return <Dashboard getToken={getToken} signedIn={Boolean(isSignedIn)} account={isSignedIn ? <UserButton /> : <SignInButton mode="modal"><button className="account-button">Sign in</button></SignInButton>} />;
}

export default function Page() {
  return process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
    ? <AuthenticatedWorkspace />
    : <Dashboard getToken={anonymous} signedIn={false} account={<span className="muted text-xs">Public research demo</span>} />;
}
