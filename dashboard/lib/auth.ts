import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { AuthToken } from './types';

const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key-change-in-production';
const ADMIN_USERNAME = process.env.ADMIN_USERNAME || 'admin';
const ADMIN_PASSWORD_HASH = process.env.ADMIN_PASSWORD_HASH || '';

/**
 * Verify username and password
 */
export async function verifyCredentials(username: string, password: string): Promise<boolean> {
  if (username !== ADMIN_USERNAME) {
    return false;
  }

  // If no hash is set, use default password 'admin' for development
  if (!ADMIN_PASSWORD_HASH) {
    return password === 'admin';
  }

  return bcrypt.compare(password, ADMIN_PASSWORD_HASH);
}

/**
 * Generate JWT token
 */
export function generateToken(username: string): string {
  const payload: AuthToken = {
    username,
    exp: Math.floor(Date.now() / 1000) + (24 * 60 * 60), // 24 hours
  };

  return jwt.sign(payload, JWT_SECRET);
}

/**
 * Verify JWT token
 */
export function verifyToken(token: string): AuthToken | null {
  try {
    const decoded = jwt.verify(token, JWT_SECRET) as AuthToken;
    return decoded;
  } catch (error) {
    return null;
  }
}

/**
 * Hash password for storage
 */
export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, 10);
}
